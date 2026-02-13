#!/usr/bin/env python3

# /// script
# requires-python = ">=3.12"
# ///

import argparse
import pathlib

from .index import index_dcdb_metadata

def main():
    parser = argparse.ArgumentParser(prog='IndexDCDBMetadata',
                                     description='Index DCDB metadata in JSON format, writing to SQLite3 database')
    parser.add_argument('source_directory', type=pathlib.Path,
                        help='Path to directory containing one or more JSON files containing DCDB ingest metadata')
    parser.add_argument('db_path', type=pathlib.Path,
                        help='Path representing file to write SQLite3 database to')
    parser.add_argument('--overwrite', action='store_true', default=False,
                        help='Overwrite database (if exists). If not set, database will be updated if it already exists')
    parser.add_argument('--verbose', action='store_true', default=False,
                        help='Produce verbose output for diagnostics')
    parser.add_argument('--skip-errors', action='store_true', default=False,
                        help='If set, treat errors as a warning and continue processing')
    args = parser.parse_args()
    index_dcdb_metadata(args.source_directory, args.db_path,
                        overwrite=args.overwrite, verbose=args.verbose, skip_errors=args.skip_errors)

if __name__ == "__main__":
    main()
