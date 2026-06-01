import typing
import functools
from dataclasses import dataclass


@dataclass(eq=True, frozen=True)
class VesselMetadataKey:
    unique_vessel_id: str
    start_time: int
    end_time: int

    def __add__(self, other: VesselMetadataKey) -> VesselMetadataKey:
        if other is None:
            return self
        if not isinstance(other, VesselMetadataKey):
            raise ValueError(f"Expected other to be of type VesselMetadataKey but it was {type(other)}")
        if self.unique_vessel_id != other.unique_vessel_id:
            raise ValueError(f"Can only add VesselMetadataKeys with the same unique_vessel_id")
        return VesselMetadataKey(
            self.unique_vessel_id,
            min(self.start_time, other.start_time),
            max(self.end_time, other.end_time)
        )

    def __radd__(self, other):
        if other is None:
            return self
        return self.__add__(other)

    def intersects(self, other):
        if other is None:
            return False
        if not isinstance(other, VesselMetadataKey):
            raise ValueError(f"Expected other to be of type VesselMetadataKey but it was {type(other)}")
        if (other.start_time <= self.start_time <= other.end_time) or \
                (other.start_time <= self.end_time <= other.end_time):
            return True
        return False


    @staticmethod
    def coalesce(keys: typing.Iterable[VesselMetadataKey]) -> VesselMetadataKey:
        return functools.reduce(lambda k1, k2: k1 + k2, keys)

@dataclass
class VesselMetadata:
    key: VesselMetadataKey
    hash: str
    metadata: dict
