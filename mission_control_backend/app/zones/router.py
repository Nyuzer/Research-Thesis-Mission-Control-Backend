from __future__ import annotations
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
import uuid
import json
import logging
import httpx
import os

from app.auth.dependencies import get_current_user, require_role
from app.auth.models import UserResponse, UserRole
from .models import ZoneCreate, ZoneUpdate, ZoneResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/maps/{map_id}/zones", tags=["zones"])

FIWARE_ORION_URL = os.getenv("FIWARE_ORION_URL", "http://localhost:1026/v2/entities")
FIWARE_SERVICE = os.getenv("FIWARE_SERVICE", "smartrobotics")
FIWARE_SERVICE_PATH = os.getenv("FIWARE_SERVICE_PATH", "/")

HEADERS = {
    "Content-Type": "application/json",
    "fiware-service": FIWARE_SERVICE,
    "fiware-servicepath": FIWARE_SERVICE_PATH,
}


def _entity_to_zone(entity: dict) -> ZoneResponse:
    def val(name: str, default=None):
        f = entity.get(name, {})
        return f.get("value", default) if isinstance(f, dict) else default

    zone_id = entity.get("id", "").replace("urn:ngsi-ld:Zone:", "")
    polygon = val("polygon", [])
    if isinstance(polygon, str):
        polygon = json.loads(polygon)

    return ZoneResponse(
        zoneId=zone_id,
        mapId=val("mapId", ""),
        name=val("name", ""),
        zoneType=val("zoneType", "parking"),
        polygon=polygon,
        speedLimit=val("speedLimit"),
        color=val("color"),
        createdBy=val("createdBy"),
        createdAt=val("createdAt", ""),
    )


@router.get("", response_model=list[ZoneResponse])
async def list_zones(map_id: str, _user: UserResponse = Depends(get_current_user)):
    params = {"type": "Zone", "q": f"mapId=={map_id}", "limit": "1000"}
    headers = {"Accept": "application/json", **{k: v for k, v in HEADERS.items() if k != "Content-Type"}}
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(FIWARE_ORION_URL, params=params, headers=headers, timeout=10.0)
            if res.status_code == 404:
                return []
            res.raise_for_status()
            return [_entity_to_zone(e) for e in res.json()]
    except httpx.HTTPStatusError:
        return []
    except Exception as e:
        logger.error(f"Error listing zones: {e}")
        return []


@router.post("", response_model=ZoneResponse, status_code=201)
async def create_zone(
    map_id: str,
    data: ZoneCreate,
    user: UserResponse = Depends(require_role(UserRole.admin, UserRole.operator)),
):
    if len(data.polygon) < 3:
        raise HTTPException(status_code=400, detail="Polygon must have at least 3 vertices")
    if data.zoneType not in ("parking", "speed_limit"):
        raise HTTPException(status_code=400, detail="zoneType must be 'parking' or 'speed_limit'")
    if data.zoneType == "speed_limit" and data.speedLimit is None:
        raise HTTPException(status_code=400, detail="speedLimit required for speed_limit zones")

    zone_id = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc).isoformat()

    entity = {
        "id": f"urn:ngsi-ld:Zone:{zone_id}",
        "type": "Zone",
        "mapId": {"type": "Text", "value": map_id},
        "name": {"type": "Text", "value": data.name},
        "zoneType": {"type": "Text", "value": data.zoneType},
        "polygon": {"type": "Text", "value": json.dumps(data.polygon)},
        "speedLimit": {"type": "Number", "value": data.speedLimit or 0},
        "color": {"type": "Text", "value": data.color or ("#3b82f640" if data.zoneType == "parking" else "#f59e0b40")},
        "createdBy": {"type": "Text", "value": user.username},
        "createdAt": {"type": "Text", "value": now},
    }

    async with httpx.AsyncClient() as client:
        res = await client.post(FIWARE_ORION_URL, json=entity, headers=HEADERS, timeout=10.0)
        if res.status_code not in (201, 204):
            raise HTTPException(status_code=500, detail=f"Failed to create zone in Orion: {res.text}")

    return ZoneResponse(
        zoneId=zone_id, mapId=map_id, name=data.name, zoneType=data.zoneType,
        polygon=data.polygon, speedLimit=data.speedLimit,
        color=entity["color"]["value"], createdBy=user.username, createdAt=now,
    )


@router.put("/{zone_id}", response_model=ZoneResponse)
async def update_zone(
    map_id: str,
    zone_id: str,
    data: ZoneUpdate,
    _user: UserResponse = Depends(require_role(UserRole.admin, UserRole.operator)),
):
    entity_id = f"urn:ngsi-ld:Zone:{zone_id}"
    attrs: dict = {}
    if data.name is not None:
        attrs["name"] = {"type": "Text", "value": data.name}
    if data.zoneType is not None:
        attrs["zoneType"] = {"type": "Text", "value": data.zoneType}
    if data.polygon is not None:
        if len(data.polygon) < 3:
            raise HTTPException(status_code=400, detail="Polygon must have at least 3 vertices")
        attrs["polygon"] = {"type": "Text", "value": json.dumps(data.polygon)}
    if data.speedLimit is not None:
        attrs["speedLimit"] = {"type": "Number", "value": data.speedLimit}
    if data.color is not None:
        attrs["color"] = {"type": "Text", "value": data.color}

    if not attrs:
        raise HTTPException(status_code=400, detail="No fields to update")

    url = f"{FIWARE_ORION_URL}/{entity_id}/attrs"
    async with httpx.AsyncClient() as client:
        res = await client.patch(url, json=attrs, headers=HEADERS, timeout=10.0)
        if res.status_code == 404:
            raise HTTPException(status_code=404, detail="Zone not found")
        if res.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail=f"Failed to update zone: {res.text}")

    # Fetch updated
    async with httpx.AsyncClient() as client:
        res = await client.get(f"{FIWARE_ORION_URL}/{entity_id}", headers={k: v for k, v in HEADERS.items() if k != "Content-Type"}, timeout=10.0)
        if res.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch updated zone")
        return _entity_to_zone(res.json())


@router.delete("/{zone_id}")
async def delete_zone(
    map_id: str,
    zone_id: str,
    _user: UserResponse = Depends(require_role(UserRole.admin, UserRole.operator)),
):
    entity_id = f"urn:ngsi-ld:Zone:{zone_id}"
    url = f"{FIWARE_ORION_URL}/{entity_id}"
    headers = {k: v for k, v in HEADERS.items() if k != "Content-Type"}
    async with httpx.AsyncClient() as client:
        res = await client.delete(url, headers=headers, timeout=10.0)
        if res.status_code == 404:
            raise HTTPException(status_code=404, detail="Zone not found")
        if res.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail=f"Failed to delete zone: {res.text}")
    return {"detail": "Zone deleted"}
