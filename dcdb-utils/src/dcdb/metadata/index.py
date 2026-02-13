from pathlib import Path

from .ingest import load_vessel_metadata

def index_dcdb_metadata(source_directory: Path, db_path: Path, *,
                        overwrite: bool):
    print(f"Using source_directory: {str(source_directory)}")
    print(f"Using db_path: {str(db_path)}")
    print(f"Using --overwrite: {overwrite}")

