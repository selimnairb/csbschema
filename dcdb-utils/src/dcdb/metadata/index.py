from pathlib import Path
import os

from .ingest import load_vessel_metadata, write_vessel_metadata_to_db
from .db import create_metadata_db, open_metadata_db

def index_dcdb_metadata(source: Path, db_path: Path, *,
                        overwrite: bool = False, verbose: bool = False, skip_errors: bool = False):
    print(f"Using source: {str(source)}, is_dir: {source.is_dir()}, is_file: {source.is_file()}")
    print(f"Using db_path: {str(db_path)}")
    print(f"Using --overwrite: {overwrite}")

    if db_path.exists():
        if overwrite:
            os.unlink(db_path)
            create_metadata_db(db_path)
    else:
        create_metadata_db(db_path)

    db = None
    try:
        db = open_metadata_db(db_path)
        cur = db.cursor()
        # Lazy-load metadata documents and write to database
        write_vessel_metadata_to_db(cur,
                                    load_vessel_metadata(source, verbose=verbose),
                                    skip_errors=skip_errors)
        db.commit()
    finally:
        if db:
            db.close()
