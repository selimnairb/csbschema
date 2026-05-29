import functools

import pytest

from dcdb.metadata import VesselMetadataKey

def test_vessel_metadata_key():
    keys: set = set()
    k: VesselMetadataKey = VesselMetadataKey(
        "AQM-687ce9f49cea48-68471861",
        1769112738000,
        1769113847000
    )
    keys.add(k)
    k_new_strt: VesselMetadataKey = VesselMetadataKey(
        "AQM-687ce9f49cea48-68471861",
        1769113847000,
        1769113847000
    )
    keys.add(k_new_strt)
    k_older_strt: VesselMetadataKey = VesselMetadataKey(
        "AQM-687ce9f49cea48-68471861",
        1769112730000,
        1769113847000
    )
    keys.add(k_older_strt)
    k_older_end: VesselMetadataKey = VesselMetadataKey(
        "AQM-687ce9f49cea48-68471861",
        1769112738000,
        1769113845000
    )
    keys.add(k_older_end)
    k_later_end: VesselMetadataKey = VesselMetadataKey(
        "AQM-687ce9f49cea48-68471861",
        1769112738000,
        1769113849000
    )
    keys.add(k_later_end)

    k_final = VesselMetadataKey.coalesce(keys)
    assert k_final.unique_vessel_id == k.unique_vessel_id
    assert k_final.start_time == k_older_strt.start_time
    assert k_final.end_time == k_later_end.end_time


def test_vessel_metadata_key_identity():
    k: VesselMetadataKey = VesselMetadataKey(
        "AQM-687ce9f49cea48-68471861",
        1769112738000,
        1769113847000
    )
    k2 = None + k
    assert k.unique_vessel_id == k2.unique_vessel_id
    assert k.start_time == k2.start_time
    assert k.end_time == k2.end_time
