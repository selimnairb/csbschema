from pathlib import Path
import sqlite3
from typing import Iterator

import pytest

from dcdb.metadata import VesselMetadataKey
from dcdb.metadata.ingest import load_vessel_metadata, write_vessel_metadata_to_db, DataIngestStats
from dcdb.metadata.db import create_metadata_db, open_metadata_db, get_metadata_entries, \
    get_vessel_entry_stats, VesselEntrySummaryStats

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
        entries = get_metadata_entries(db, unique_vessel_id=unique_vessel_id)
        assert len(entries) == 0
        stats = DataIngestStats()
        write_vessel_metadata_to_db(db, stats, vessel_meta)
        entries = get_metadata_entries(db, unique_vessel_id=unique_vessel_id)
        assert len(entries) == 1
        all_entries = get_metadata_entries(db)
        assert len(all_entries) == 4

        # Now ingest a file with the same metadata as an existing entry, but with an older start time.
        # This should result in the record being updated to have the older start time.
        existing_entry = entries[0]
        doc_path_ex1_older: Path = data_path / 'example1-older-start-time'
        stats = DataIngestStats()
        write_vessel_metadata_to_db(db, stats, load_vessel_metadata(doc_path_ex1_older, stats))
        new_entries = get_metadata_entries(db, unique_vessel_id=unique_vessel_id)
        assert len(new_entries) == 1
        new_entry_st = new_entries[0]
        assert new_entry_st.key.start_time < existing_entry.key.start_time
        assert new_entry_st.key.end_time == existing_entry.key.end_time
        assert new_entry_st.hash == existing_entry.hash

        # Now ingest a file with the same metadata as an existing entry, but with a later end time.
        # This should result in the record being updated to have the older start time.
        doc_path_ex1_later: Path = data_path / 'example1-later-end-time'
        stats = DataIngestStats()
        write_vessel_metadata_to_db(db, stats, load_vessel_metadata(doc_path_ex1_later, stats))
        new_entries = get_metadata_entries(db, unique_vessel_id=unique_vessel_id)
        assert len(new_entries) == 1
        new_entry_ed = new_entries[0]
        # Start time was updated with the previous import, so we can't compare to the baseline.
        assert new_entry_ed.key.start_time == new_entry_st.key.start_time
        assert new_entry_ed.key.end_time > existing_entry.key.end_time
        assert new_entry_ed.hash == existing_entry.hash

        # Now ingest a file with the same, though rounded, metadata and a newer start time.
        # This should result in no change to the database.
        entries = get_metadata_entries(db, unique_vessel_id=unique_vessel_id)
        assert len(entries) == 1
        existing_entry = entries[0]
        doc_path_ex1_rounded: Path = data_path / 'example1-rounded-same-hash'
        stats = DataIngestStats()
        write_vessel_metadata_to_db(db, stats, load_vessel_metadata(doc_path_ex1_rounded, stats))
        new_entries = get_metadata_entries(db, unique_vessel_id=unique_vessel_id)
        assert len(new_entries) == 1
        new_entry = new_entries[0]
        assert new_entry.key.start_time == existing_entry.key.start_time
        assert new_entry.key.end_time == existing_entry.key.end_time
        assert new_entry.hash == existing_entry.hash

        # Finally, test the case where a new metadata entry for an existing vessel is received
        # that has different metadata, but the same start time and end time
        # This should result in the database
        doc_path_ex1_diff_hash: Path = data_path / 'example1-same-start-different-hash'
        stats = DataIngestStats()
        write_vessel_metadata_to_db(db, stats, load_vessel_metadata(doc_path_ex1_diff_hash, stats))
        new_entries = get_metadata_entries(db, unique_vessel_id=unique_vessel_id)
        assert len(new_entries) == 2

    finally:
        db.close()
