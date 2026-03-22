from __future__ import annotations
from typing import List
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


def _compute_centroid(polygon):
    """Compute centroid of a polygon [[x,y], ...]."""
    if not polygon:
        return None
    n = len(polygon)
    cx = sum(p[0] for p in polygon) / n
    cy = sum(p[1] for p in polygon) / n
    return [cx, cy]


def _entity_to_zone(entity: dict) -> ZoneResponse:
    def val(name: str, default=None):
        f = entity.get(name, {})
        return f.get("value", default) if isinstance(f, dict) else default

    zone_id = entity.get("id", "").replace("urn:ngsi-ld:Zone:", "")
    polygon = val("polygon", [])
    if isinstance(polygon, str):
        polygon = json.loads(polygon)

    goal_point = val("goalPoint")
    if isinstance(goal_point, str):
        try:
            goal_point = json.loads(goal_point)
        except (json.JSONDecodeError, TypeError):
            goal_point = None

    is_default_raw = val("isDefault")
    is_default = None
    if is_default_raw is not None:
        if isinstance(is_default_raw, bool):
            is_default = is_default_raw
        elif isinstance(is_default_raw, str):
            is_default = is_default_raw.lower() == "true"

    return ZoneResponse(
        zoneId=zone_id,
        mapId=val("mapId", ""),
        name=val("name", ""),
        zoneType=val("zoneType", "parking"),
        polygon=polygon,
        speedLimit=val("speedLimit"),
        color=val("color"),
        goalPoint=goal_point,
        isDefault=is_default,
        createdBy=val("createdBy"),
        createdAt=val("createdAt", ""),
    )


async def _clear_other_defaults(map_id: str, exclude_zone_id: str):
    """Reset isDefault=false for all other zones on this map."""
    params = {"type": "Zone", "q": "mapId=={};isDefault==true".format(map_id), "limit": "1000"}
    read_headers = {"Accept": "application/json", "fiware-service": FIWARE_SERVICE, "fiware-servicepath": FIWARE_SERVICE_PATH}
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(FIWARE_ORION_URL, params=params, headers=read_headers, timeout=10.0)
            if res.status_code == 404:
                return
            res.raise_for_status()
            for entity in res.json():
                eid = entity.get("id", "")
                zid = eid.replace("urn:ngsi-ld:Zone:", "")
                if zid != exclude_zone_id:
                    url = "{}/{}/attrs".format(FIWARE_ORION_URL, eid)
                    await client.patch(url, json={"isDefault": {"type": "Text", "value": "false"}}, headers=HEADERS, timeout=10.0)
    except Exception as e:
        logger.error("Error clearing other defaults: {}".format(e))


@router.get("", response_model=List[ZoneResponse])
async def list_zones(map_id: str, _user: UserResponse = Depends(get_current_user)):
    params = {"type": "Zone", "q": "mapId=={}".format(map_id), "limit": "1000"}
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
        logger.error("Error listing zones: {}".format(e))
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

    # For parking zones, compute centroid as goalPoint if not provided
    goal_point = data.goalPoint
    if data.zoneType == "parking" and goal_point is None:
        goal_point = _compute_centroid(data.polygon)

    is_default = data.isDefault or False

    # Enforce single default per map
    if is_default:
        await _clear_other_defaults(map_id, zone_id)

    entity = {
        "id": "urn:ngsi-ld:Zone:{}".format(zone_id),
        "type": "Zone",
        "mapId": {"type": "Text", "value": map_id},
        "name": {"type": "Text", "value": data.name},
        "zoneType": {"type": "Text", "value": data.zoneType},
        "polygon": {"type": "Text", "value": json.dumps(data.polygon)},
        "speedLimit": {"type": "Number", "value": data.speedLimit or 0},
        "color": {"type": "Text", "value": data.color or ("#3b82f640" if data.zoneType == "parking" else "#f59e0b40")},
        "goalPoint": {"type": "Text", "value": json.dumps(goal_point) if goal_point else ""},
        "isDefault": {"type": "Text", "value": "true" if is_default else "false"},
        "createdBy": {"type": "Text", "value": user.username},
        "createdAt": {"type": "Text", "value": now},
    }

    async with httpx.AsyncClient() as client:
        res = await client.post(FIWARE_ORION_URL, json=entity, headers=HEADERS, timeout=10.0)
        if res.status_code not in (201, 204):
            raise HTTPException(status_code=500, detail="Failed to create zone in Orion: {}".format(res.text))

    return ZoneResponse(
        zoneId=zone_id, mapId=map_id, name=data.name, zoneType=data.zoneType,
        polygon=data.polygon, speedLimit=data.speedLimit,
        color=entity["color"]["value"], goalPoint=goal_point,
        isDefault=is_default, createdBy=user.username, createdAt=now,
    )


@router.put("/{zone_id}", response_model=ZoneResponse)
async def update_zone(
    map_id: str,
    zone_id: str,
    data: ZoneUpdate,
    _user: UserResponse = Depends(require_role(UserRole.admin, UserRole.operator)),
):
    entity_id = "urn:ngsi-ld:Zone:{}".format(zone_id)
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
    if data.goalPoint is not None:
        attrs["goalPoint"] = {"type": "Text", "value": json.dumps(data.goalPoint)}
    if data.isDefault is not None:
        attrs["isDefault"] = {"type": "Text", "value": "true" if data.isDefault else "false"}
        if data.isDefault:
            await _clear_other_defaults(map_id, zone_id)

    if not attrs:
        raise HTTPException(status_code=400, detail="No fields to update")

    url = "{}/{}/attrs".format(FIWARE_ORION_URL, entity_id)
    async with httpx.AsyncClient() as client:
        res = await client.patch(url, json=attrs, headers=HEADERS, timeout=10.0)
        if res.status_code == 404:
            raise HTTPException(status_code=404, detail="Zone not found")
        if res.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Failed to update zone: {}".format(res.text))

    # Fetch updated
    async with httpx.AsyncClient() as client:
        res = await client.get("{}/{}".format(FIWARE_ORION_URL, entity_id), headers={k: v for k, v in HEADERS.items() if k != "Content-Type"}, timeout=10.0)
        if res.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch updated zone")
        return _entity_to_zone(res.json())


@router.delete("/{zone_id}")
async def delete_zone(
    map_id: str,
    zone_id: str,
    _user: UserResponse = Depends(require_role(UserRole.admin, UserRole.operator)),
):
    entity_id = "urn:ngsi-ld:Zone:{}".format(zone_id)
    url = "{}/{}".format(FIWARE_ORION_URL, entity_id)
    headers = {k: v for k, v in HEADERS.items() if k != "Content-Type"}
    async with httpx.AsyncClient() as client:
        res = await client.delete(url, headers=headers, timeout=10.0)
        if res.status_code == 404:
            raise HTTPException(status_code=404, detail="Zone not found")
        if res.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Failed to delete zone: {}".format(res.text))
    return {"detail": "Zone deleted"}
