# Indexing DCDB CSB metadata into SQLite3 databases

## Requirements
The scripts and tests require the following:

- Python 3.12 or later
- [json_stream](https://pypi.org/project/json-stream/)
- [pytest](https://docs.pytest.org/en/stable/) (installation instructions are in the 'Running tests' section below)

## Indexing metadata
The DCDB metadata indexer can read DCDB metadata from a single JSON file (containing an array of JSON objects at its 
root) efficiently using `json_stream`, so there is no need to extract metadata objects into separate files. To index 
DCDB metadata from a single JSON file in an SQLite3 database by running the following Python script from the 
[src](./src) directory:
```shell
time python3 -m dcdb.metadata \
  ../local/csbMetadataPayload_20170101-20260325.json \
  ../local/csbMetadataPayload_20170101-20260325.sqlite3 \
  --verbose --overwrite --skip-errors | tee ../local/csbMetadataPayload_20170101-20260325.log
...
...
...
python3 -m dcdb.metadata ../local/csbMetadataPayload_20170101-20260325.json    440.20s user 239.07s system 89% cpu 12:36.84 total
tee ../local/csbMetadataPayload_20170101-20260325.log  0.01s user 0.49s system 0% cpu 12:36.84 total
```

The other options are described using the `--help` option:
```shell
python3 -m dcdb.metadata --help
usage: IndexDCDBMetadata [-h] [--overwrite] [--verbose] [--skip-errors] source db_path

Index DCDB metadata in JSON format, writing to SQLite3 database

positional arguments:
  source         Path to a single JSON file containing a JSON array of object representing DCDB ingest metadata entries or a directory containing one or more JSON files containing DCDB ingest metadata.
  db_path        Path representing file to write SQLite3 database to

options:
  -h, --help     show this help message and exit
  --overwrite    Overwrite database (if exists). If not set, database will be updated if it already exists
  --verbose      Produce verbose output for diagnostics
  --skip-errors  If set, treat errors as a warning and continue processing
```

### Incremental indexing
```shell
# First chunk
time python3 -m dcdb.metadata \
  ../local/csbMetadataPayload_20170101-20260325-pretty-subset-pt1.json \
  ../local/csbMetadataPayload_20170101-20260325-subset-incremental.sqlite3 \
  --verbose --overwrite --skip-errors | tee ../local/csbMetadataPayload_20170101-20260325-pretty-subset-pt1.log
# Second chunk  
time python3 -m dcdb.metadata \
  ../local/csbMetadataPayload_20170101-20260325-pretty-subset-pt2.json \
  ../local/csbMetadataPayload_20170101-20260325-subset-incremental.sqlite3 \
  --verbose --skip-errors | tee ../local/csbMetadataPayload_20170101-20260325-pretty-subset-pt2.log
# Third chunk
time python3 -m dcdb.metadata \
  ../local/csbMetadataPayload_20170101-20260325-pretty-subset-pt3.json \
  ../local/csbMetadataPayload_20170101-20260325-subset-incremental.sqlite3 \
  --verbose --skip-errors | tee ../local/csbMetadataPayload_20170101-20260325-pretty-subset-pt3.log
```

Sequential run to compare to:
```shell
time python3 -m dcdb.metadata \
  ../local/csbMetadataPayload_20170101-20260325-pretty-subset.json \
  ../local/csbMetadataPayload_20170101-20260325-subset-singleton.sqlite3 \
  --verbose --overwrite --skip-errors | tee ../local/csbMetadataPayload_20170101-20260325-pretty-subset-singleton.log
```

Dump to CSV and compare:
```shell
sqlite3 -csv ../local/csbMetadataPayload_20170101-20260325-subset-incremental.sqlite3 'SELECT unique_vessel_id, hash, start_time, end_time FROM vessels ORDER BY unique_vessel_id, hash, start_time, end_time;' > ../local/csbMetadataPayload_20170101-20260325-subset-incremental.csv

sqlite3 -csv ../local/csbMetadataPayload_20170101-20260325-subset-singleton.sqlite3 'SELECT unique_vessel_id, hash, start_time, end_time FROM vessels ORDER BY unique_vessel_id, hash, start_time, end_time;' > ../local/csbMetadataPayload_20170101-20260325-subset-singleton.csv 

diff -s ../local/csbMetadataPayload_20170101-20260325-subset-singleton.csv \
  ../local/csbMetadataPayload_20170101-20260325-subset-incremental.csv
Files ../local/csbMetadataPayload_20170101-20260325-subset-singleton.csv and ../local/csbMetadataPayload_20170101-20260325-subset-incremental.csv are identical
```

No differences!  Processing all records from one file results in functionally the same 
database as when processing incrementally.

### Incremental indexing with overlap between files
```shell
# First chunk
time python3 -m dcdb.metadata \
  ../local/csbMetadataPayload_20170101-20260325-pretty-subset-overlap-pt1.json \
  ../local/csbMetadataPayload_20170101-20260325-subset-overlap-incremental.sqlite3 \
  --verbose --overwrite --skip-errors | tee ../local/csbMetadataPayload_20170101-20260325-pretty-subset-overlap-pt1.log
# Second chunk  
time python3 -m dcdb.metadata \
  ../local/csbMetadataPayload_20170101-20260325-pretty-subset-overlap-pt2.json \
  ../local/csbMetadataPayload_20170101-20260325-subset-overlap-incremental.sqlite3 \
  --verbose --skip-errors | tee ../local/csbMetadataPayload_20170101-20260325-pretty-subset-overlap-pt2.log
# Third chunk
time python3 -m dcdb.metadata \
  ../local/csbMetadataPayload_20170101-20260325-pretty-subset-overlap-pt3.json \
  ../local/csbMetadataPayload_20170101-20260325-subset-overlap-incremental.sqlite3 \
  --verbose --skip-errors | tee ../local/csbMetadataPayload_20170101-20260325-pretty-subset-overlap-pt3.log
```

Dump to CSV and compare:
```shell
sqlite3 -csv ../local/csbMetadataPayload_20170101-20260325-subset-overlap-incremental.sqlite3 'SELECT unique_vessel_id, hash, start_time, end_time FROM vessels ORDER BY unique_vessel_id, hash, start_time, end_time;' > ../local/csbMetadataPayload_20170101-20260325-subset-overlap-incremental.csv

diff -s ../local/csbMetadataPayload_20170101-20260325-subset-singleton.csv \
  ../local/csbMetadataPayload_20170101-20260325-subset-overlap-incremental.csv

Files ../local/csbMetadataPayload_20170101-20260325-subset-singleton.csv and ../local/csbMetadataPayload_20170101-20260325-subset-overlap-incremental.csv are identical
```

No differences!  Processing all records from one file results in functionally the same 
database as when processing overlapped data incrementally.

## Using the database
To use the CSB index metadata database created above, you can use your language's bindings for SQLite3. Additionally, 
to explore the database you can use the `sqlite3` command line tool:
```shell
$ sqlite3 csbMetadataPayload_20260201-20260210.sqlite3
-- Loading resources from $HOME/.sqliterc
SQLite version 3.43.2 2023-10-10 13:08:14
Enter ".help" for usage hints.
sqlite> select count(*) from vessels;
count(*)    
------------
43          
sqlite> select * from vessels where unique_vessel_id='SIGNALK-ac020bdf-5c0e-4c82-844f-1db2bc73383a';
unique_vesse  obs_time          hash                                                          metadata                                                    
------------  ----------------  ------------------------------------------------------------  ------------------------------------------------------------
SIGNALK-ac02  2022-01-03 12:06  3e54c4275c2fe88c21dabb7ebeae5e00755241aaa0fffdf16eb935e13f99  {"platform": {"IDNumber": "211692440", "IDType": "MMSI", "le
0bdf-5c0e-4c  :31+00:00         7aeb                                                          ngth": 9.36, "name": "Lille Oe", "positionOffsetsDocumented"
82-844f-1db2                                                                                  : true, "sensors": [{"draft": 1.55, "frequency": 50, "make":
bc73383a                                                                                       "Garmin", "model": "P79", "position": [0.5, 2, 0.3], "type"
                                                                                              : "Sounder"}, {"make": "B&G", "model": "ZG100", "position": 
                                                                                              [0, 9, 1], "type": "GNSS"}], "type": "Sailing", "uniqueID": 
                                                                                              "SIGNALK-ac020bdf-5c0e-4c82-844f-1db2bc73383a"}, "trustedNod
                                                                                              e": {"convention": "GeoJSON CSB 3.1", "dataLicense": "CC0 1.
                                                                                              0", "navigationCRS": "EPSG:4326", "providerEmail": "bathy@op
                                                                                              enwaters.io", "providerLogger": "crowd-depth (https://github
                                                                                              .com/openwatersio/crowd-depth)", "providerLoggerVersion": "1
                                                                                              .0.0-beta.12", "providerOrganizationName": "Open Water Softw
                                                                                              are", "uniqueVesselID": "SIGNALK-ac020bdf-5c0e-4c82-844f-1db
                                                                                              2bc73383a", "verticalReferenceOfDepth": "Waterline", "vessel
                                                                                              PositionReferencePoint": "Transducer"}}                     
```

## Running tests
First, install the test requirements in a virtual environment:
```shell
python3.12 -m venv venv-test
source venv-test/bin/activate
pip install -r requirements-test.txt
```

> Python 3.13+ should also work.

Then run `pytest` from the same directory as this README file:
```shell
pytest tests/test_*.py
==================================================================== test session starts ====================================================================
platform darwin -- Python 3.12.12, pytest-9.0.2, pluggy-1.6.0
rootdir: /.../csbschema/dcdb-utils/tests
configfile: pytest.ini
collected 1 item                                                                                                                                            

tests/test_metadata_ingest.py .                                                                                                                       [100%]

===================================================================== warnings summary ======================================================================
test_metadata_ingest.py::test_write_vessel_metadata_to_db
test_metadata_ingest.py::test_write_vessel_metadata_to_db
test_metadata_ingest.py::test_write_vessel_metadata_to_db
test_metadata_ingest.py::test_write_vessel_metadata_to_db
test_metadata_ingest.py::test_write_vessel_metadata_to_db
  /.../csbschema/dcdb-utils/tests/../src/dcdb/metadata/ingest.py:72: DeprecationWarning: The default datetime adapter is deprecated as of Python 3.12; see the sqlite3 documentation for suggested replacement recipes
    db_cur.execute('INSERT INTO vessels VALUES(?, ?, ?, ?)', data)

test_metadata_ingest.py::test_write_vessel_metadata_to_db
  /.../csbschema/dcdb-utils/tests/../src/dcdb/metadata/ingest.py:81: DeprecationWarning: The default datetime adapter is deprecated as of Python 3.12; see the sqlite3 documentation for suggested replacement recipes
    db_cur.execute('UPDATE vessels SET obs_time=? WHERE unique_vessel_id=? AND hash=?',

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=============================================================== 1 passed, 6 warnings in 0.05s ===============================================================
```
