import copy
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
import hashlib
from typing import Iterator, Sequence
import sys

import json_stream.base

from ..metadata import VesselMetadataKey
from .extraction import get_unique_vessel_id, get_start_end_times, sort_dict_by_keys
from . import db

def round_numeric(meta: dict|list, *,
                  exclude_keys: tuple = ('time', 'fileType', 'submissionInfo', 'dataProcessed')):
    if isinstance(meta, dict):
        for k, v in meta.items():
            if k in exclude_keys:
                continue
            if isinstance(v, dict|list):
                round_numeric(v, exclude_keys=exclude_keys)
            elif isinstance(v, float):
                meta[k] = round(v, 3)
    elif isinstance(meta, list):
        for i, e in enumerate(meta):
            if isinstance(e, dict|list):
                round_numeric(e, exclude_keys=exclude_keys)
            elif isinstance(e, float):
                meta[i] = round(e, 3)


def iterate_json_objects(doc_root: Path, *,
                         verbose: bool = False) -> Iterator[tuple[str, dict]]:
    if doc_root.is_dir():
        for doc in doc_root.glob('*.json'):
            if verbose:
                sys.stdout.write(f"Attempting to read file {str(doc)}...")
            with doc.open(mode='rt') as f:
                yield str(doc), json.load(f)
    elif doc_root.is_file():
        doc = str(doc_root)
        with doc_root.open(mode='rt') as f:
            data = json_stream.load(f)
            if isinstance(data, json_stream.base.TransientStreamingJSONObject):
                # The file contains a single JSON object at its root, yield it
                yield doc, json_stream.to_standard_types(data)
            elif isinstance(data, json_stream.base.TransientStreamingJSONList):
                # The file contains a JSON array at its root, iterate elements to yield them as dicts
                for i, d in enumerate(data):
                    yield f"{doc}[{i}]", json_stream.to_standard_types(d)
            else:
                raise ValueError(f"Expected either a JSON object or list at the root of {doc}, but found {type(data)}.")
    else:
        raise ValueError("doc_root must be either a directory or a file, but was neither.")


def load_vessel_metadata(doc_root: Path,
                         stats: DataIngestStats,
                         *,
                         verbose: bool = False) -> Iterator[tuple[VesselMetadataKey, dict]]:
    for doc, doc_data in iterate_json_objects(doc_root, verbose=verbose):
        try:
            uniqueId = get_unique_vessel_id(doc_data)
        except ValueError as e:
            stats.records_warning += 1
            print(f"WARNING: Unable to read unique ID for file {str(doc)} due to error {str(e)}, skipping...")
            continue
        if uniqueId is None:
            stats.records_warning += 1
            print(f"WARNING: No unique ID for file {str(doc)}, skipping...")
            continue
        if verbose:
            sys.stdout.write(f"Processing vessel metadata for {uniqueId} in file {str(doc)}...")
        try:
            start_time, end_time = get_start_end_times(doc_data)
            if start_time < 0:
                stats.records_warning += 1
                print(f"\n\tWARNING: Encountered start time < 0 ({start_time}) for {uniqueId} for file {str(doc)}, skipping...")
                continue
        except ValueError as e:
            stats.records_warning += 1
            print(f"\n\tWARNING: Unable to read start,end time for {uniqueId} for file {str(doc)} due to error {str(e)}, skipping...")
            continue
        if start_time is None or end_time is None:
            stats.records_warning += 1
            print(f"\n\tWARNING: Expected start and end time for {uniqueId} for file {str(doc)} to not be None, "
                  "but one of them was None, skipping...")
            continue
        # Sort metadata so that hashing is consistent for the same set of metadata
        doc_meta: dict = sort_dict_by_keys(doc_data, {})
        # Round numeric values in metadata to normalize essentially similar metadata
        round_numeric(doc_meta)
        # print(f"sorted doc_meta: {json.dumps(doc_meta)}\n\n")
        key = VesselMetadataKey(
            unique_vessel_id=uniqueId,
            start_time=start_time,
            end_time=end_time,
        )
        if verbose:
            sys.stdout.write('done.\n')
        yield key, doc_meta


@dataclass
class DataIngestStats:
    records_total: int = 0
    records_written: int = 0
    records_warning: int = 0
    records_error: int = 0


def remove_key(d: dict, key_compound: str):
    """
    Removes a key or a nested key (if present) from a dictionary.

    This function deletes a key-value pair from a dictionary. If the key to be
    removed is nested within the dictionary, it can be specified in a compound
    form separated by dots (e.g., "key1.key2.key3"). The function will traverse
    the dictionary hierarchy and remove the specified key when found. If the key
    is not found, no error will be raised.

    Args:
        d (dict): The dictionary from which the key will be removed.
        key_compound (str): A dot-separated string representing the key or
            nested key to remove.
    """
    try:
        key_components = key_compound.split('.')
        num_components = len(key_components)
        if num_components == 1:
            del d[key_components[0]]
        else:
            tmp_dict = d[key_components[0]]
            component_count: int = 1
            for component in key_components[1:]:
                component_count += 1
                if component_count >= num_components:
                    del tmp_dict[component]
                else:
                    tmp_dict = tmp_dict[component]
    except KeyError:
        ...

def hash_metadata(md: dict, *,
                  exclude_keys: Sequence[str] = ('providerContactPoint.loggerVersion',)) -> str:
    m = hashlib.sha3_256()
    md_cpy: dict = copy.deepcopy(md)
    for excluded in exclude_keys:
        remove_key(md_cpy, excluded)
    metadata: str = json.dumps(md_cpy)
    m.update(bytes(metadata, 'utf-8'))
    return m.hexdigest()


def write_vessel_metadata_to_db(conn: sqlite3.Connection, stats: DataIngestStats, vessel_meta: Iterator[tuple[VesselMetadataKey, dict]], *,
                                skip_errors: bool = False):
    db_cur: sqlite3.Cursor = conn.cursor()
    updated: bool = False
    for k, v in vessel_meta:
        stats.records_total += 1
        md_hash = hash_metadata(v)
        metadata: str = json.dumps(v)
        # Create-update logic is as follows
        #  - If a vessel entry exists for this (unique_vessel_id, start_time, end_time, hash): SKIP
        #  If a vessel entry exists for the same (unique_vessel_id, start_time, hash)
        #       but with an earlier end_time: SKIP
        #  - Else, If a vessel entry exists for the same (unique_vessel_id, start_time, hash)
        #       but with a later end_time: UPDATE existing entry with the later end_time
        #  - Else, INSERT
        try:
            entries = db.get_metadata_entries(db_cur, k.unique_vessel_id,
                                              start_time=k.start_time,
                                              end_time=k.end_time,
                                              md_hash=md_hash)
            if len(entries) > 0:
                first = entries[0]
                print(f"\tWARNING: A new metadata entry for existing vessel {k.unique_vessel_id} was received\n"
                      f"\tthat is identical, SKIPPING.\n\tExisting metadata is {first.metadata}\n"
                      f"\tNew metadata is: {metadata}")
                continue
            else:
                # Query all entries for this vessel with the current hash so that we can check for any
                # updates that we can make to an existing record (because it covers an overlapping start/end
                # time interval).
                entries = db.get_metadata_entries(db_cur, k.unique_vessel_id,
                                                  md_hash=md_hash)
                if len(entries) > 0:
                    for e in entries:
                        # NOTE: This won't work as the integrity error will stop us from applying all of the sequential
                        # updates to reach the desired end state. We need to work out the desired end state, then
                        # apply it to the DB once.
                        if e.key.end_time < k.end_time:
                            # A vessel entry exists for the same (unique_vessel_id, hash)
                            # but with an earlier end_time: UPDATE the end_time
                            updating = True
                            db.update_vessel_entry(db_cur, k, e)
                            updating = False
                        if e.key.start_time > k.start_time:
                            # A vessel entry exists for the same (unique_vessel_id, hash)
                            # but with a later start_time: UPDATE the start_time
                            updating = True
                            db.update_vessel_entry(db_cur, k, e)
                            updating = False
                else:
                    # No vessel entry exists for this (unique_vessel_id, hash) INSERT
                    db.add_entry_for_vessel(db_cur, k.unique_vessel_id,
                                            k.start_time, k.end_time, md_hash, metadata)
                    stats.records_written += 1
        except sqlite3.IntegrityError as e:
            if updating:
                # Got an integrity error while updating, which means the update we want to make
                # already exists in the DB, so we can ignore...
                ...
            print(f"Encountered error: {e}, giving up...")
            raise e
            # if not skip_errors:
            #     raise e
            # else:
            #     md_extant, sub_time_cd_extant, hash_extant = db.get_metadata_for_unique_vessel_id_and_start_time(db_cur, k.unique_vessel_id, k.start_time)
            #     if sub_time_cd_extant is None or hash_extant is None:
            #         stats.records_error += 1
            #         raise Exception(f"ERROR: expected metadata to exist for unique vessel ID {k.unique_vessel_id} "
            #                         f"at obs time {k.start_time}, but it did not.")
            #     print((f"\tWARNING: A new metadata entry for existing vessel {k.unique_vessel_id} was received\n"
            #            f"\tthat has different metadata, but the same start time ({k.start_time}) "
            #            "as an entry already in the database. "))
            #     if k.submit_timecode > sub_time_cd_extant:
            #         # The submit timecode of the new metadata record is newer than what is in the database,
            #         # so we likely want to use this record, but first, let's make sure it's not materially worse
            #         # than what has already been encountered...
            #         print(f"\t\tExisting metadata record timecode {sub_time_cd_extant} is OLDER than new record "
            #               f"timecode {k.submit_timecode}")
            #         update_metadata: bool = True
            #         if 'platform' in v:
            #             v_platform = v['platform']
            #             # First, look for field "platform.shipDraft", don't allow draft to be set from >0 to 0 and
            #             # don't allow a larger draft to replace a smaller draft. Again, both metadata records have
            #             # the same start time, so would apply to the same range of observations, so we want to err
            #             # on the side of a smaller draft value since this would result in shoaler depths after
            #             # correcting for draft.
            #             if 'shipDraft' in v_platform:
            #                 if 'platform' in md_extant:
            #                     if 'shipDraft' in md_extant['platform']:
            #                         ext_draft = md_extant['platform']['shipDraft']
            #                         new_draft = v_platform['shipDraft']
            #                         if ext_draft > 0:
            #                             if new_draft == 0:
            #                                 print(f"\t\tSkipping update, reason: Don't allow draft to be set from > 0 to 0")
            #                                 update_metadata = False
            #                             elif ext_draft < new_draft:
            #                                 print(f"\t\tSkipping update, reason: Don't allow a larger draft to replace a smaller draft")
            #                                 update_metadata = False
            #             elif 'platform' in md_extant:
            #                 if 'shipDraft' in md_extant['platform']:
            #                     if md_extant['platform']['shipDraft'] > 0:
            #                         print(f"\t\tSkipping update, reason: Don't allow draft to be set from > 0 to NOTHING")
            #                         update_metadata = False
            #
            #             # Second, look for platform.sensors.type="Sounder", with peer platform.sensors.draft, i.e.:
            #             # "sensors": [
            #             #       {
            #             #         "draft": 0.518,
            #             #         "type": "Sounder"
            #             #       }
            #             #     ]
            #             # Don't allow the sounder draft to be set from >0 to 0.
            #             if 'sensors' in v_platform:
            #                 v_sounder_draft: float = 0.0
            #                 ext_sounder_draft: float = 0.0
            #                 for s in v_platform['sensors']:
            #                     if s['type'] == 'Sounder':
            #                         v_sounder_draft = s.get('draft', 0.0)
            #                 if 'platform' in md_extant:
            #                     if 'sensors' in md_extant['platform']:
            #                         for s in md_extant['platform']['sensors']:
            #                             if s['type'] == 'Sounder':
            #                                 ext_sounder_draft = s.get('draft', 0.0)
            #                 if v_sounder_draft == 0 and ext_sounder_draft > 0:
            #                     print(f"\t\tSkipping update, reason: Don't allow the sounder draft to be set from >0 to 0.")
            #                     update_metadata = False
            #
            #         if update_metadata:
            #             print(f"\t\tUpdating metadata record in database from:\n"
            #                   f"\t\t{str(md_extant)}\n"
            #                   "\t\tTo:\n"
            #                   f"\t\t{metadata}\n")
            #             db.update_metadata_for_vessel(db_cur, k.unique_vessel_id, md_hash, k.submit_timecode,
            #                                           metadata, hash_extant)
            #             stats.records_written += 1
            #             continue
            #     else:
            #         print(f"\t\tExisting metadata record timecode {sub_time_cd_extant} is NEWER than new record timecode {k.submit_timecode}")
            #
            #     print(("\t\tSKIPPING: Since this can lead to ambiguous metadata, this metadata entry will be skipped. "
            #            "New entry is:\n"
            #            f"\t\t{metadata}\n"
            #            "\t\tDB entry is:\n"
            #            f"\t\t{str(md_extant)}\n"
            #            f"\tError was: {str(e)}, continuing to process the next file..."))
            #     stats.records_warning += 1
