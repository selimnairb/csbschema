import sqlite3
from pathlib import Path


def create_metadata_db(db_file: Path):
    with sqlite3.connect(db_file) as con:
        cur = con.cursor()
        cur.execute(
    '''CREATE TABLE 
           vessels(unique_vessel_id TEXT, obs_time DATETIME, hash TEXT, metadata JSON, 
                   PRIMARY KEY(unique_vessel_id, obs_time))'''
        )

def open_metadata_db(db_file: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_file)

