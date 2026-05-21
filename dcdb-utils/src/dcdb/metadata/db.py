import sqlite3
from pathlib import Path
import json
from io import StringIO
from enum import StrEnum

from dcdb.metadata import VesselMetadataKey, VesselMetadata

class Predicate(StrEnum):
    EQ = '='
    GT = '>'
    GTE = '>='
    LT = '<'
    LTE = '<='
    NE = '!='


def create_metadata_db(db_file: Path):
    with sqlite3.connect(db_file) as con:
        cur = con.cursor()
        try:
            cur.executescript('''
            BEGIN;
            CREATE TABLE 
                vessels(unique_vessel_id TEXT, start_time INTEGER, end_time INTEGER,
                        hash TEXT, metadata JSON,
                        PRIMARY KEY (unique_vessel_id, start_time, end_time),
                        CONSTRAINT vessels_md_uniq UNIQUE (unique_vessel_id, start_time, end_time, submit_timecode, 
                                                           hash));
            CREATE INDEX IF NOT EXISTS vessels_uv_id_idx ON vessels (unique_vessel_id);
            CREATE INDEX IF NOT EXISTS vessels_strt_tm_idx ON vessels (start_time);
            CREATE INDEX IF NOT EXISTS vessels_end_tm_idx ON vessels (end_time);
            CREATE INDEX IF NOT EXISTS vessels_hash_cd_idx ON vessels (hash);
            COMMIT;    
            ''')
        except sqlite3.OperationalError as e:
            print(f"Unable to create table due to error {str(e)}")
            raise e

def open_metadata_db(db_file: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_file, autocommit=True)
    con.row_factory = sqlite3.Row
    return con

def add_entry_for_vessel(cur: sqlite3.Cursor,
                         unique_vessel_id: str,
                         start_time: int,
                         end_time: int,
                         hash: str,
                         metadata: str):
    cur.execute('INSERT INTO vessels VALUES(?, ?, ?, ?, ?)',
                (unique_vessel_id, start_time, end_time, hash, metadata))

# def update_start_time_for_vessel(cur: sqlite3.Cursor,
#                                start_time: int,
#                                unique_vessel_id: str,
#                                hash: str):
#     cur.execute('UPDATE vessels SET start_time=? WHERE unique_vessel_id=? AND hash=?',
#                 (start_time, unique_vessel_id, hash))
#


def update_vessel_entry(cur: sqlite3.Cursor,
                                  key: VesselMetadataKey,
                                  new_val: VesselMetadata):
    cur.execute('''
                BEGIN;
                UPDATE vessels SET start_time=?, 
                                   end_time=?,
                                   hash=?,
                                   metadata=?
                WHERE unique_vessel_id=? AND start_time=? AND end_time=?;
                COMMIT;    
                ''',
                (new_val.key.start_time, new_val.key.end_time, new_val.hash, new_val.metadata,
                           key.unique_vessel_id, key.start_time, key.end_time))


def get_metadata_entries(cur: sqlite3.Cursor, unique_vessel_id: str, *,
                         start_time: int | None = None,
                         pred_start_time: Predicate = Predicate.EQ,
                         end_time: int | None = None,
                         pred_end_time: Predicate = Predicate.EQ,
                         md_hash: str | None = None,
                         pred_md_hash: Predicate = Predicate.EQ) -> list[VesselMetadata]:
    entries = []
    args = []
    builder = StringIO()
    builder.write('SELECT * from vessels WHERE unique_vessel_id=?')
    args.append(unique_vessel_id)
    if start_time:
        builder.write(f" AND start_time{str(pred_start_time)}?")
        args.append(start_time)
    if end_time:
        builder.write(f" AND end_time{str(pred_end_time)}?")
        args.append(end_time)
    if md_hash:
        builder.write(f" AND hash{str(pred_md_hash)}?")
        args.append(md_hash)
    try:
        results = cur.execute(builder.getvalue(), args)
        for r in results.fetchall():
            key = VesselMetadataKey(r['unique_vessel_id'],
                                    r['start_time'],
                                    r['end_time'])
            value = VesselMetadata(key,
                                   r['hash'],
                                   json.loads(r['metadata']))
            entries.append(value)
    except Exception as e:
        raise e
    finally:
        builder.close()

    return entries

def get_metadata_for_unique_vessel_id_and_start_time(cur: sqlite3.Cursor,
                                                   unique_vessel_id: str,
                                                   start_time: int) -> tuple[dict, str|None, str|None]:
    c = cur.execute('SELECT metadata, submit_timecode, hash FROM vessels WHERE unique_vessel_id=? AND start_time=?',
                       (unique_vessel_id, start_time))
    result = c.fetchone()
    if result is None or len(result) < 1:
        return {}, None, None
    return json.loads(result[0]), result[1], result[2]
