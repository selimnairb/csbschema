import sqlite3
from pathlib import Path
import json
from datetime import datetime

from dcdb.metadata import VesselMetadataKey, VesselMetadata


def create_metadata_db(db_file: Path):
    with sqlite3.connect(db_file) as con:
        cur = con.cursor()
        cur.executescript('''
        BEGIN;
        CREATE TABLE 
           vessels(unique_vessel_id TEXT, obs_time INTEGER, submit_time_code TEXT, hash TEXT, metadata JSON, 
                   PRIMARY KEY(unique_vessel_id, hash),
                   CONSTRAINT vessels_uv_id_obs_time_constr UNIQUE (unique_vessel_id, obs_time));
        CREATE INDEX IF NOT EXISTS vessels_uv_id_idx ON vessels (unique_vessel_id);
        CREATE INDEX IF NOT EXISTS vessels_submit_time_cd_idx ON vessels (submit_time_code); 
        COMMIT;    
        ''')

def open_metadata_db(db_file: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_file, autocommit=True)

def add_entry_for_vessel(cur: sqlite3.Cursor,
                         unique_vessel_id: str,
                         obs_time: int,
                         submit_time_code: str,
                         hash: str,
                         metadata: str):
    cur.execute('INSERT INTO vessels VALUES(?, ?, ?, ?, ?)',
                (unique_vessel_id, obs_time, submit_time_code, hash, metadata))

def update_obs_time_for_vessel(cur: sqlite3.Cursor,
                               obs_time: int,
                               unique_vessel_id: str,
                               hash: str):
    cur.execute('UPDATE vessels SET obs_time=? WHERE unique_vessel_id=? AND hash=?',
                (obs_time, unique_vessel_id, hash))

def update_metadata_for_vessel(cur: sqlite3.Cursor,
                              unique_vessel_id: str,
                              hash_new: str,
                              submit_time_code: str,
                              metadata: str,
                              hash_extant: str):
    try:
        cur.execute('UPDATE vessels SET metadata=?, hash=?, submit_time_code=? WHERE unique_vessel_id=? AND hash=?',
                    (metadata, hash_new, submit_time_code, unique_vessel_id, hash_extant))
    except sqlite3.IntegrityError as e:
        # TODO: Fix
        print(f"Caught {str(e)} in update_metadata_for_vessel...")

def get_entries_for_unique_vessel_id(cur: sqlite3.Cursor, unique_vessel_id: str, md_hash: str|None = None) -> list[VesselMetadata]:
    entries = []
    if md_hash:
        results = cur.execute('SELECT * from vessels WHERE unique_vessel_id=? AND hash=?',
                              (unique_vessel_id, md_hash))
    else:
        results = cur.execute('SELECT * from vessels WHERE unique_vessel_id=?', (unique_vessel_id,))
    for result in results.fetchall():
        key = VesselMetadataKey(result[0],
                                result[1],
                                result[2])
        value = VesselMetadata(key,
                               result[3],
                               json.loads(result[4]))
        entries.append(value)
    return entries

def get_metadata_for_unique_vessel_id_and_obs_time(cur: sqlite3.Cursor,
                                                   unique_vessel_id: str,
                                                   obs_time: int) -> tuple[dict, str|None, str|None]:
    c = cur.execute('SELECT metadata, submit_time_code, hash FROM vessels WHERE unique_vessel_id=? AND obs_time=?',
                       (unique_vessel_id, obs_time))
    result = c.fetchone()
    if result is None or len(result) < 1:
        return {}, None, None
    return json.loads(result[0]), result[1], result[2]
