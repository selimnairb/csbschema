from dataclasses import dataclass


@dataclass(eq=True, frozen=True)
class VesselMetadataKey:
    unique_vessel_id: str
    start_time: int
    end_time: int

@dataclass
class VesselMetadata:
    key: VesselMetadataKey
    hash: str
    metadata: dict
