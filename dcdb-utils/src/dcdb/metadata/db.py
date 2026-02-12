import sqlite3
from pathlib import Path
import json

from dcdb.metadata import VesselMetadataKey, VesselMetadata


def create_metadata_db(db_file: Path):
    with sqlite3.connect(db_file) as con:
        cur = con.cursor()
        cur.executescript('''
        BEGIN;
        CREATE TABLE 
           vessels(unique_vessel_id TEXT, obs_time DATETIME, hash TEXT, metadata JSON, 
                   PRIMARY KEY(unique_vessel_id, hash));
        CREATE INDEX IF NOT EXISTS vessels_uv_id_idx ON vessels (unique_vessel_id); 
        COMMIT;    
        ''')

def open_metadata_db(db_file: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_file)

def get_entries_for_unique_vessel_id(cur: sqlite3.Cursor, unique_vessel_id: str, md_hash: str|None = None) -> list[VesselMetadata]:
    entries = []
    if md_hash:
        results = cur.execute('SELECT * from vessels WHERE unique_vessel_id=? AND hash=?',
                              (unique_vessel_id, md_hash))
    else:
        results = cur.execute('SELECT * from vessels WHERE unique_vessel_id=?', (unique_vessel_id,))
    for result in results.fetchall():
        key = VesselMetadataKey(result[0],
                                result[1])
        value = VesselMetadata(key,
                               result[2],
                               json.loads(result[3]))
        entries.append(value)
    return entries
