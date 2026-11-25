import functools

import pytest

from dcdb.metadata import VesselMetadataKey

def test_vessel_metadata_key():
    keys: set = set()
    md_hash = '1q2w3e4r5t6y'
    k: VesselMetadataKey = VesselMetadataKey(
        "AQM-687ce9f49cea48-68471861",
        1769112738000,
        1769113847000,
        md_hash
    )
    keys.add(k)
    k_new_strt: VesselMetadataKey = VesselMetadataKey(
        "AQM-687ce9f49cea48-68471861",
        1769113847000,
        1769113847000,
        md_hash
    )
    keys.add(k_new_strt)
    k_older_strt: VesselMetadataKey = VesselMetadataKey(
        "AQM-687ce9f49cea48-68471861",
        1769112730000,
        1769113847000,
        md_hash
    )
    keys.add(k_older_strt)
    k_older_end: VesselMetadataKey = VesselMetadataKey(
        "AQM-687ce9f49cea48-68471861",
        1769112738000,
        1769113845000,
        md_hash
    )
    keys.add(k_older_end)
    k_later_end: VesselMetadataKey = VesselMetadataKey(
        "AQM-687ce9f49cea48-68471861",
        1769112738000,
        1769113849000,
        md_hash
    )
    keys.add(k_later_end)

    k_final = VesselMetadataKey.coalesce(keys)
    assert k_final.unique_vessel_id == k.unique_vessel_id
    assert k_final.start_time == k_older_strt.start_time
    assert k_final.end_time == k_later_end.end_time


def test_vessel_metadata_key_identity():
    md_hash = '1q2w3e4r5t6y'
    k: VesselMetadataKey = VesselMetadataKey(
        "AQM-687ce9f49cea48-68471861",
        1769112738000,
        1769113847000,
        md_hash
    )
    k2 = None + k
    k3 = k + None
    assert id(k) == id(k2) == id(k3)
    assert k.unique_vessel_id == k2.unique_vessel_id
    assert k.start_time == k2.start_time
    assert k.end_time == k2.end_time


def test_vessel_metadata_key_intersect():
    md_hash = '1q2w3e4r5t6y'
    k1: VesselMetadataKey = VesselMetadataKey(
        "one",
        10,
        20,
        md_hash
    )
    k2: VesselMetadataKey = VesselMetadataKey(
        "one",
        5,
        10,
        md_hash
    )
    k3: VesselMetadataKey = VesselMetadataKey(
        "one",
        15,
        20,
        md_hash
    )
    k4: VesselMetadataKey = VesselMetadataKey(
        "one",
        5,
        11,
        md_hash
    )
    k5: VesselMetadataKey = VesselMetadataKey(
        "one",
        15,
        21,
        md_hash
    )
    assert k1.intersects(k2)
    assert k1.intersects(k3)
    assert not k2.intersects(k3)
    assert k1.intersects(k4)
    assert k1.intersects(k5)
