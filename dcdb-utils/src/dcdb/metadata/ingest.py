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
from .db import get_entries_for_unique_vessel_id


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
        if verbose:
            sys.stdout.write(f"Processing vessel metadata for {uniqueId} in file {str(doc)}...")
        try:
            start_time, end_time = get_start_end_times(doc_data)
        except ValueError as e:
            print(f"\n\tWARNING: Unable to read start,end time for file {str(doc)} due to error {str(e)}, skipping...")
            continue
        if start_time is None or end_time is None:
            print(
                f"\n\tWARNING: Expected start and end time for file {str(doc)} to not be None, but one of them was None, skipping...")
            continue
        # Sort metadata so that hashing is consistent for the same set of metadata
        doc_meta: dict = sort_dict_by_keys(doc_data, {})
        # Round numeric values in metadata to normalize essentially similar metadata
        round_numeric(doc_meta)
        # print(f"sorted doc_meta: {json.dumps(doc_meta)}\n\n")
        key = VesselMetadataKey(
            unique_vessel_id=uniqueId,
            obs_time=start_time
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


def hash_metadata(md: dict, *,
                  exclude_keys: Sequence[str] = ('providerContactPoint.loggerVersion')) -> str:
    m = hashlib.sha3_256()
    metadata: str = json.dumps(md)
    m.update(bytes(metadata, 'utf-8'))
    return m.hexdigest()


def write_vessel_metadata_to_db(db: sqlite3.Connection, vessel_meta: Iterator[tuple[VesselMetadataKey, dict]], *,
                                skip_errors: bool = False) -> DataIngestStats:
    stats = DataIngestStats()
    db_cur: sqlite3.Cursor = db.cursor()
    for k, v in vessel_meta:
        stats.records_total += 1
        md_hash = hash_metadata(v)
        metadata: str = json.dumps(v)
        data = [k.unique_vessel_id, k.obs_time, md_hash, metadata]
        # Create-update logic is as follows
        #  - If no vessel entry exists for this (unique_vessel_id, obs_time, hash) INSERT
        #  - If a vessel entry exists for this (unique_vessel_id, hash):
        #    - if new.obs_time < vessel.obs_time:
        #      - Update vessel.obs_time = new_obs_time
        #    - else:
        #      - Ignore update
        #  - If more than one vessel entry exists for this (unique_vessel_id, hash), ERROR
        try:
            entries = get_entries_for_unique_vessel_id(db_cur, k.unique_vessel_id, md_hash)
            if len(entries) == 0:
                # No vessel entry exists for this (unique_vessel_id, obs_time, hash) INSERT
                db_cur.execute('INSERT INTO vessels VALUES(?, ?, ?, ?)', data)
                stats.records_written += 1
            elif len(entries) > 1:
                # If more than one vessel entry exists for this (unique_vessel_id, hash), ERROR
                stats.records_error += 1
                raise Exception(f"ERROR: Expected at most one vessel metadata entry for unique vessel_id {k.unique_vessel_id} and hash {md_hash}, but found {len(entries)}")
            else:
                entry = entries[0]
                if k.obs_time < entry.key.obs_time:
                    # A vessel entry exists for this (unique_vessel_id, hash) and new.obs_time < vessel.obs_time
                    # Update vessel.obs_time = new_obs_time
                    db_cur.execute('UPDATE vessels SET obs_time=? WHERE unique_vessel_id=? AND hash=?',
                                   (k.obs_time, k.unique_vessel_id, md_hash))
                    stats.records_written += 1
        except sqlite3.IntegrityError as e:
            if not skip_errors:
                raise e
            else:
                c = db_cur.execute('SELECT metadata FROM vessels WHERE unique_vessel_id=? AND obs_time=?',
                                        (k.unique_vessel_id, k.obs_time))
                result = c.fetchone()
                print((f"\tWARNING: A new metadata entry for existing vessel {k.unique_vessel_id} was received\n"
                       f"\tthat has different metadata, but the same start time ({k.obs_time}) as an entry already in the database.\n"
                       "\tSince this lead to ambiguous metadata, this metadata entry will be skipped. Data was:\n"
                       f"\t\t{metadata}\nDB entry was:\n"
                       f"\t\t{result[0]}\n"
                       f"\tError was: {str(e)}, continuing to process the next file..."))
                stats.records_warning += 1
    return stats
