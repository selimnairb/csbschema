from dataclasses import dataclass
from datetime import datetime


@dataclass(eq=True, frozen=True)
class VesselMetadataKey:
    unique_vessel_id: str
    obs_time: datetime

@dataclass
class VesselMetadata:
    key: VesselMetadataKey
    hash: str
    metadata: dict
