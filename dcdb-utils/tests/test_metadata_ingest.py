from pathlib import Path
import sqlite3
from typing import Iterator

import pytest

from dcdb.metadata import VesselMetadataKey
from dcdb.metadata.ingest import load_vessel_metadata, write_vessel_metadata_to_db, DataIngestStats
from dcdb.metadata.db import create_metadata_db, open_metadata_db, get_entries_for_unique_vessel_id

from fixtures import data_path, temp_path


def test_write_vessel_metadata_to_db(data_path, temp_path):
    doc_path_ex1: Path = data_path / 'example1'
    stats = DataIngestStats()
    vessel_meta: Iterator[tuple[VesselMetadataKey, dict]] = load_vessel_metadata(doc_path_ex1, stats)

    db_path = temp_path / 'vessel_meta.db'
    create_metadata_db(db_path)
    db = None
    try:
        db = open_metadata_db(db_path)
        assert db is not None
        cur = db.cursor()

        unique_vessel_id: str = 'AQM-687ce9f49cea48-68471861'
        entries = get_entries_for_unique_vessel_id(cur, unique_vessel_id)
        assert len(entries) == 0
        stats = DataIngestStats()
        write_vessel_metadata_to_db(db, stats, vessel_meta)
        entries = get_entries_for_unique_vessel_id(cur, unique_vessel_id)
        assert len(entries) == 1

        # Now ingest a file with the same metadata as an existing entry, but with a later start time.
        # This should result in no change to the database.
        existing_entry = entries[0]
        doc_path_ex1_newer: Path = data_path / 'example1-newer-start-time'
        stats = DataIngestStats()
        write_vessel_metadata_to_db(db, stats, load_vessel_metadata(doc_path_ex1_newer, stats))
        new_entries = get_entries_for_unique_vessel_id(cur, unique_vessel_id)
        assert len(new_entries) == 1
        new_entry = new_entries[0]
        assert new_entry.key.obs_time == existing_entry.key.obs_time
        assert new_entry.hash == existing_entry.hash

        # Now ingest a file with the same metadata as an existing entry, but with an older start time.
        # This should result in the older start time being added to the db.
        doc_path_ex1_older: Path = data_path / 'example1-older-start-time'
        stats = DataIngestStats()
        write_vessel_metadata_to_db(db, stats, load_vessel_metadata(doc_path_ex1_older, stats))
        new_entries = get_entries_for_unique_vessel_id(cur, unique_vessel_id)
        assert len(new_entries) == 1
        new_entry = new_entries[0]
        assert new_entry.key.obs_time < existing_entry.key.obs_time
        assert new_entry.hash == existing_entry.hash

        # Now ingest a file with the same, though rounded, metadata and a newer start time.
        # This should result in no change to the database.
        entries = get_entries_for_unique_vessel_id(cur, unique_vessel_id)
        assert len(entries) == 1
        existing_entry = entries[0]
        doc_path_ex1_rounded: Path = data_path / 'example1-rounded-same-hash'
        stats = DataIngestStats()
        write_vessel_metadata_to_db(db, stats, load_vessel_metadata(doc_path_ex1_rounded, stats))
        new_entries = get_entries_for_unique_vessel_id(cur, unique_vessel_id)
        assert len(new_entries) == 1
        new_entry = new_entries[0]
        assert new_entry.key.obs_time == existing_entry.key.obs_time
        assert new_entry.hash == existing_entry.hash

        # Finally, test the case where a new metadata entry for an existing vessel is received
        # that has different metadata, but the same start time -- this should result in the database
        # not allowing the metadata to be inserted.
        doc_path_ex1_diff_hash: Path = data_path / 'example1-same-start-different-hash'
        stats = DataIngestStats()
        vessel_meta_diff_hash = load_vessel_metadata(doc_path_ex1_diff_hash, stats)
        exception_thrown = False
        try:
            write_vessel_metadata_to_db(db, stats, vessel_meta_diff_hash)
        except sqlite3.IntegrityError:
            exception_thrown = True
        assert exception_thrown

    finally:
        db.close()
