from pathlib import Path

import pytest

from dcdb.metadata import VesselMetadataKey
from dcdb.metadata.ingest import load_vessel_metadata, write_vessel_metadata_to_db
from dcdb.metadata.db import create_metadata_db, open_metadata_db, get_entries_for_unique_vessel_id

from fixtures import data_path, temp_path


def test_load_vessel_metadata(data_path):
    doc_path_ex1: Path = data_path / 'example1'

    vessel_meta: dict[VesselMetadataKey, dict] = load_vessel_metadata(doc_path_ex1)
    assert len(vessel_meta) == 5


def test_write_vessel_metadata_to_db(data_path, temp_path):
    doc_path_ex1: Path = data_path / 'example1'
    vessel_meta: dict[VesselMetadataKey, dict] = load_vessel_metadata(doc_path_ex1)

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

        write_vessel_metadata_to_db(cur, vessel_meta)
        entries = get_entries_for_unique_vessel_id(cur, unique_vessel_id)
        assert len(entries) == 2
    finally:
        db.close()
