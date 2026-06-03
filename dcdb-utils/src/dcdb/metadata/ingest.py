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
        docs = sorted([doc for doc in doc_root.glob('*.json')])
        for doc in docs:
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
                elem: int = 0
                for i, d in enumerate(data):
                    elem += 1
                    try:
                        yield f"{doc}[{i}]", json_stream.to_standard_types(d)
                    except ValueError as e:
                        print(f"ERROR: Reading element {elem} from file {doc}, Attempting to read next element. "
                              f"error was: {str(e)}")
                        continue
            else:
                raise ValueError(f"Expected either a JSON object or list at the root of {doc}, but found {type(data)}.")
    else:
        raise ValueError("doc_root must be either a directory or a file, but was neither.")


def load_vessel_metadata(doc_root: Path,
                         stats: DataIngestStats,
                         *,
                         verbose: bool = False) -> Iterator[tuple[VesselMetadataKey, dict]]:
    for doc, doc_data in iterate_json_objects(doc_root, verbose=verbose):
        stats.records_total += 1
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
        # Round numeric values in metadata to normalize essentially identical metadata
        round_numeric(doc_meta)
        # print(f"sorted doc_meta: {json.dumps(doc_meta)}\n\n")
        key = VesselMetadataKey(
            unique_vessel_id=uniqueId,
            start_time=start_time,
            end_time=end_time,
            md_hash=hash_metadata(doc_meta)
        )
        if verbose:
            sys.stdout.write('done.\n')
        yield key, doc_meta


@dataclass
class DataIngestStats:
    records_total: int = 0
    records_written: int = 0
    records_intersected: int = 0
    records_updated: int = 0
    records_deleted: int = 0
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


def _merge_deltas(deltas: dict[VesselMetadataKey, VesselMetadataKey],
                  to_delete: set[VesselMetadataKey]) -> \
        dict[VesselMetadataKey, VesselMetadataKey]:
    num_deltas = len(deltas)
    if num_deltas >= 2:
        num_deltas_ = num_deltas - 1
        keys = [k for k in deltas.keys()]
        values = [v for v in deltas.values()]
        new_deltas: dict[VesselMetadataKey, VesselMetadataKey] = {}
        i = 0
        has_isect = False
        while i < num_deltas_:
            v1 = values[i]
            v2 = values[i + 1]
            if v1.intersects(v2):
                has_isect = True
                new_deltas[keys[i]] = v1 + v2
                to_delete.add(keys[i + 1])
                i += 2
            else:
                new_deltas[keys[i]] = v1
                i += 1
        while i < num_deltas:
            new_deltas[keys[i]] = values[i]
            i += 1
        if has_isect:
            return _merge_deltas(new_deltas, to_delete)
        else:
            return new_deltas
    else:
        return deltas


def write_vessel_metadata_to_db(con: sqlite3.Connection, stats: DataIngestStats, vessel_meta: Iterator[tuple[VesselMetadataKey, dict]], *,
                                skip_errors: bool = False):
    deltas: dict = {}
    try:
        for k, v in vessel_meta:
            metadata: str = json.dumps(v)
            # Create-update logic is as follows:
            #  - If a vessel entry exists for this (unique_vessel_id, start_time, end_time, hash): SKIP
            #  - Else, If a vessel entry intersects in time with a given (unique_vessel_id, start_time, end_time,
            #    and hash): UPDATE existing entry to be the union
            #    - If UPDATE has already been applied for another existing entry, delete the entry being updated.
            #  - Else, INSERT
            intersected: bool = False
            exists: bool = False
            for entry in db.get_metadata_entry_keys_intersecting(con,
                                                                 k.unique_vessel_id,
                                                                 k.md_hash,
                                                                 k.start_time,
                                                                 k.end_time):
                if k == entry:
                    exists = True
                else:
                    intersected = True
                    delta = (k + entry)
                    # Need to check whether `deltas.get(entry, None)` intersects with `delta` before adding.
                    existing_delta = deltas.get(entry, None)
                    if existing_delta is None:
                        deltas[entry] = delta
                    else:
                        if delta.intersects(existing_delta):
                            deltas[entry] = existing_delta + delta
                        else:
                            # The delta does not intersect with the existing delta
                            # Do we: A. Insert k, or insert the delta?
                            # Is this even possible to reach??
                            raise NotImplementedError(f"Delta {str(delta)} for new entry {str(k)} intersects "
                                                      f"with {str(entry)} but does not intersect with existing "
                                                      f"delta {str(existing_delta)}.")

                    stats.records_intersected += 1
            if not intersected and not exists:
                try:
                    db.add_entry_for_vessel(con, k.unique_vessel_id,
                                            k.start_time, k.end_time, k.md_hash, metadata)
                    stats.records_written += 1
                except sqlite3.IntegrityError as e:
                    print(f"WARNING: Metadata entry with key {str(k)} already exists in database.")

        # Before merging deltas, let's compare each delta to DB entries with the same unique_vessel_id and hash,
        # now that we've seen all entries in the current file. This way, we can merge deltas with any entries
        # that weren't known about when the delta was created.
        to_delete_db: set[VesselMetadataKey] = set()
        to_delete_delta: set[VesselMetadataKey] = set()
        for old_key, delta in deltas.items():
            for entry in db.get_metadata_entry_keys_intersecting(con,
                                                                 delta.unique_vessel_id,
                                                                 delta.md_hash,
                                                                 delta.start_time,
                                                                 delta.end_time):
                if delta == entry:
                    # The delta already exists in the DB due to an entry being added after the delta was created,
                    # so we can simply mark this delta for deletion and mark old_key for deletion since it is no
                    # longer needed.
                    to_delete_db.add(old_key)
                    # Can't delete the delta here as it can raise a RunTime error, see
                    # [here](https://docs.python.org/3/library/stdtypes.html#dictionary-view-objects)
                    to_delete_delta.add(old_key)
                    # No sense looking at any further DB entries since we just deleted this delta
                    break
                # delta intersects with entry, update delta to be the union of delta and entry, and mark entry
                # for deletion as it will be obsoleted by delta.
                deltas[old_key] += entry
                to_delete_db.add(entry)
                stats.records_intersected += 1

        for d in to_delete_delta:
            del deltas[d]
        # Before applying updates, see if any updates intersect in time, and if so, merge them, marking for deletion
        # any existing records whose delta was merged with another.
        deltas = _merge_deltas(deltas, to_delete_db)

        # Apply any updates
        for old_key, delta in deltas.items():
            try:
                db.update_vessel_entry_start_time_end_time(con, old_key, delta)
                stats.records_updated += 1
            except sqlite3.IntegrityError as e:
                print(f"Deleting {str(old_key)} as {str(delta)} has already been applied.")
                db.delete_vessel_entry(con, old_key)
                stats.records_deleted += 1
        # Process any deletes
        for d in to_delete_db:
            db.delete_vessel_entry(con, d)
            stats.records_deleted += 1

    except sqlite3.IntegrityError as e:
        print(f"Encountered error: {str(e)}, giving up...")
        raise e
