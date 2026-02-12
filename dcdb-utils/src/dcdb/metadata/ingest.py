import json
import sqlite3
from pathlib import Path
import hashlib

from ..metadata import VesselMetadataKey
from .extraction import get_unique_vessel_id, get_start_end_times, sort_dict_by_keys


def load_vessel_metadata(doc_root: Path) -> dict[VesselMetadataKey, dict]:
    vessel_meta: dict[VesselMetadataKey, dict] = {}

    for doc in doc_root.glob('*.json'):
        # print(str(doc))
        with doc.open(mode='rt') as f:
            doc_data: dict = json.load(f)

        try:
            uniqueId = get_unique_vessel_id(doc_data)
        except ValueError as e:
            print(f"Unable to read unique ID for file {str(doc)} due to error {str(e)}, skipping...")
            continue
        if uniqueId is None:
            print(f"No unique ID for file {str(doc)}, skipping...")
            continue

        # print(f"Unique Id for file {str(doc)} is {uniqueId}")

        try:
            start_time, end_time = get_start_end_times(doc_data)
        except ValueError as e:
            print(f"Unable to read start,end time for file {str(doc)} due to error {str(e)}, skipping...")
            continue
        if start_time is None or end_time is None:
            print(
                f"Expected start and end time for file {str(doc)} to not be None, but one of them was None, skipping...")
            continue

        # print(f"start, end time for file {str(doc)} is {start_time}, {end_time}.")

        # print(f"raw doc_meta: {json.dumps(doc_meta)}\n\n")
        doc_meta: dict = sort_dict_by_keys(doc_data, {})
        # print(f"sorted doc_meta: {json.dumps(doc_meta)}\n\n")
        key = VesselMetadataKey(
            unique_vessel_id=uniqueId,
            obs_time=start_time
        )
        vessel_meta[key] = doc_meta

    return vessel_meta


def write_vessel_metadata_to_db(vessel_meta: dict[VesselMetadataKey, dict], db_cur: sqlite3.Cursor):
    for k, v in vessel_meta.items():
        m = hashlib.sha3_256()
        metadata: str = json.dumps(v)
        m.update(bytes(metadata, 'utf-8'))
        metadata_hash: str = m.hexdigest()
        data = [k.unique_vessel_id, k.obs_time, metadata_hash, metadata]
        # TODO: Implement create-update logic
        #  - If no vessel entry exists for this (unique_vessel_id, obs_time, hash) INSERT
        #  - If a vessel entry exists for this (unique_vessel_id, hash):
        #    - if new.obs_time < vessel.obs_time:
        #      - Update vessel.obs_time = new_obs_time
        #    - else:
        #      - Ignore update
        #  - If more than one vessel entry exists for this (unique_vessel_id, hash), ERROR
        db_cur.execute("INSERT INTO vessels VALUES(?, ?, ?, ?)", data)
