from pydantic import BaseModel
from typing import List, Optional


class ZoneCreate(BaseModel):
    name: str
    zoneType: str  # "parking" or "speed_limit"
    polygon: List[List[float]]  # List of [x, y] vertices in EPSG:25832
    speedLimit: Optional[float] = None  # m/s, only for speed_limit zones
    color: Optional[str] = None


class ZoneUpdate(BaseModel):
    name: Optional[str] = None
    zoneType: Optional[str] = None
    polygon: Optional[List[List[float]]] = None
    speedLimit: Optional[float] = None
    color: Optional[str] = None


class ZoneResponse(BaseModel):
    zoneId: str
    mapId: str
    name: str
    zoneType: str
    polygon: List[List[float]]
    speedLimit: Optional[float] = None
    color: Optional[str] = None
    createdBy: Optional[str] = None
    createdAt: str
