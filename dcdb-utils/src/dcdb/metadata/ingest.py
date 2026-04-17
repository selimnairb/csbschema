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


def load_vessel_metadata(doc_root: Path, *,
                         verbose: bool = False) -> Iterator[tuple[VesselMetadataKey, dict]]:
    for doc, doc_data in iterate_json_objects(doc_root, verbose=verbose):
        try:
            uniqueId = get_unique_vessel_id(doc_data)
        except ValueError as e:
            print(f"WARNING: Unable to read unique ID for file {str(doc)} due to error {str(e)}, skipping...")
            continue
        if uniqueId is None:
            print(f"WARNING: No unique ID for file {str(doc)}, skipping...")
            continue
        if 'submissionInfo' not in doc_data:
            print(f"WARNING: Expected 'submissionInfo' in metadata but none was found. Skipping record. Data was: {str(doc)}")
            continue
        if 'timeCode' not in doc_data['submissionInfo']:
            print(f"WARNING: Expected 'timeCode' in 'submissionInfo' metadata, but none was found. Skipping record. Data was: {str(doc)}")
            continue
        submit_time_code: str = doc_data['submissionInfo']['timeCode']
        if verbose:
            sys.stdout.write(f"Processing vessel metadata for {uniqueId} in file {str(doc)}...")
        try:
            start_time, end_time = get_start_end_times(doc_data)
            if start_time < 0:
                print(f"\n\tWARNING: Encountered start time < 0 ({start_time}) for {uniqueId} for file {str(doc)}, skipping...")
                continue
        except ValueError as e:
            print(f"\n\tWARNING: Unable to read start,end time for {uniqueId} for file {str(doc)} due to error {str(e)}, skipping...")
            continue
        if start_time is None or end_time is None:
            print(
                f"\n\tWARNING: Expected start and end time for {uniqueId} for file {str(doc)} to not be None, but one of them was None, skipping...")
            continue
        # Sort metadata so that hashing is consistent for the same set of metadata
        doc_meta: dict = sort_dict_by_keys(doc_data, {})
        # Round numeric values in metadata to normalize essentially similar metadata
        round_numeric(doc_meta)
        # print(f"sorted doc_meta: {json.dumps(doc_meta)}\n\n")
        key = VesselMetadataKey(
            unique_vessel_id=uniqueId,
            obs_time=start_time,
            submit_time_code=submit_time_code
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


def write_vessel_metadata_to_db(conn: sqlite3.Connection, vessel_meta: Iterator[tuple[VesselMetadataKey, dict]], *,
                                skip_errors: bool = False) -> DataIngestStats:
    stats = DataIngestStats()
    db_cur: sqlite3.Cursor = conn.cursor()
    for k, v in vessel_meta:
        stats.records_total += 1
        md_hash = hash_metadata(v)
        metadata: str = json.dumps(v)
        # Create-update logic is as follows
        #  - If no vessel entry exists for this (unique_vessel_id, obs_time, hash) INSERT
        #  - If a vessel entry exists for this (unique_vessel_id, hash):
        #    - if new.obs_time < vessel.obs_time:
        #      - Update vessel.obs_time = new_obs_time
        #    - else:
        #      - Ignore update
        #  - If more than one vessel entry exists for this (unique_vessel_id, hash), ERROR
        try:
            entries = db.get_entries_for_unique_vessel_id(db_cur, k.unique_vessel_id, md_hash)
            if len(entries) == 0:
                # No vessel entry exists for this (unique_vessel_id, obs_time, hash) INSERT
                db.add_entry_for_vessel(db_cur, k.unique_vessel_id, k.obs_time, k.submit_time_code, md_hash, metadata)
                stats.records_written += 1
            elif len(entries) > 1:
                # If more than one vessel entry exists for this (unique_vessel_id, hash), ERROR
                stats.records_error += 1
                raise Exception("ERROR: Expected at most one vessel metadata entry for unique vessel ID "
                                f"{k.unique_vessel_id} and hash {md_hash}, but found {len(entries)}")
            else:
                entry = entries[0]
                if k.obs_time < entry.key.obs_time:
                    # A vessel entry exists for this (unique_vessel_id, hash) and new.obs_time < vessel.obs_time
                    # Update vessel.obs_time = new_obs_time
                    db.update_obs_time_for_vessel(db_cur, k.obs_time, k.unique_vessel_id, md_hash)
                    stats.records_written += 1
        except sqlite3.IntegrityError as e:
            if not skip_errors:
                raise e
            else:
                md_extant, sub_time_cd_extant, hash_extant = db.get_metadata_for_unique_vessel_id_and_obs_time(db_cur, k.unique_vessel_id, k.obs_time)
                if sub_time_cd_extant is None or hash_extant is None:
                    stats.records_error += 1
                    raise Exception(f"ERROR: expected metadata to exist for unique vessel ID {k.unique_vessel_id} "
                                    f"at obs time {k.obs_time}, but it did not.")
                print((f"\tWARNING: A new metadata entry for existing vessel {k.unique_vessel_id} was received\n"
                       f"\tthat has different metadata, but the same start time ({k.obs_time}) "
                       "as an entry already in the database. "))
                if k.submit_time_code > sub_time_cd_extant:
                    # if k.unique_vessel_id == 'ROSEP-48fa5fe0-5a79-4dab-b334-d44ac4c4d2bc':
                    #     import pdb; pdb.set_trace()
                    # The submit timecode of the new metadata record is newer than what is in the database,
                    # so we likely want to use this record, but first, let's make sure it's not materially worse
                    # than what has already been encountered
                    print(f"\t\tExisting metadata record timecode {sub_time_cd_extant} is OLDER than new record "
                          f"timecode {k.submit_time_code}")
                    update_metadata: bool = True
                    if 'platform' in v:
                        v_platform = v['platform']
                        # First, look for field "platform.shipDraft", don't allow draft to be set from >0 to 0 and
                        # don't allow a larger draft to replace a smaller draft. Again, both metadata records have
                        # the same start time, so would apply to the same range of observations, so we want to err
                        # on the side of a smaller draft value since this would result in shoaler depths after
                        # correcting for draft.
                        if 'shipDraft' in v_platform:
                            if 'platform' in md_extant:
                                if 'shipDraft' in md_extant['platform']:
                                    ext_draft = md_extant['platform']['shipDraft']
                                    new_draft = v_platform['shipDraft']
                                    if ext_draft > 0:
                                        if new_draft == 0:
                                            # Don't allow draft to be set from > 0 to 0
                                            print(f"\t\tSkipping update, reason: Don't allow draft to be set from > 0 to 0")
                                            update_metadata = False
                                        elif ext_draft < new_draft:
                                            # Don't allow a larger draft to replace a smaller draft
                                            print(f"\t\tSkipping update, reason: Don't allow a larger draft to replace a smaller draft")
                                            update_metadata = False
                        elif 'platform' in md_extant:
                            if 'shipDraft' in md_extant['platform']:
                                if md_extant['platform']['shipDraft'] > 0:
                                    # Don't allow draft to be set from > 0 to NOTHING
                                    print(f"\t\tSkipping update, reason: Don't allow draft to be set from > 0 to NOTHING")
                                    update_metadata = False

                        # Second, look for platform.sensors.type="Sounder", with peer platform.sensors.draft, i.e.:
                        # "sensors": [
                        #       {
                        #         "draft": 0.518,
                        #         "type": "Sounder"
                        #       }
                        #     ]
                        # Don't allow the sounder draft to be set from >0 to 0.
                        if 'sensors' in v_platform:
                            v_sounder_draft: float = 0.0
                            ext_sounder_draft: float = 0.0
                            for s in v_platform['sensors']:
                                if s['type'] == 'Sounder':
                                    v_sounder_draft = s.get('draft', 0.0)
                            if 'platform' in md_extant:
                                if 'sensors' in md_extant['platform']:
                                    for s in md_extant['platform']['sensors']:
                                        if s['type'] == 'Sounder':
                                            ext_sounder_draft = s.get('draft', 0.0)
                            if v_sounder_draft == 0 and ext_sounder_draft > 0:
                                # Don't allow the sounder draft to be set from >0 to 0.
                                print(f"\t\tSkipping update, reason: Don't allow the sounder draft to be set from >0 to 0.")
                                update_metadata = False

                    if update_metadata:
                        print(f"\t\tUpdating metadata record in database from:\n"
                              f"\t\t{str(md_extant)}\n"
                              "\t\tTo:\n"
                              f"\t\t{metadata}\n")
                        db.update_metadata_for_vessel(db_cur, k.unique_vessel_id, md_hash, k.submit_time_code,
                                                      metadata, hash_extant)
                        stats.records_written += 1
                        continue
                else:
                    print(f"\t\tExisting metadata record timecode {sub_time_cd_extant} is NEWER than new record timecode {k.submit_time_code}")

                print(("\t\tSKIPPING: Since this can lead to ambiguous metadata, this metadata entry will be skipped. "
                       "New entry is:\n"
                       f"\t\t{metadata}\n"
                       "\t\tDB entry is:\n"
                       f"\t\t{str(md_extant)}\n"
                       f"\tError was: {str(e)}, continuing to process the next file..."))
                stats.records_warning += 1
    return stats
