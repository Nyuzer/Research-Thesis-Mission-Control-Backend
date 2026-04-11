from fastapi import APIRouter, HTTPException, Depends, Body
import logging
import json
import os
import uuid
from datetime import datetime, timezone
import httpx

from app.auth.dependencies import get_current_user, require_role
from app.auth.models import UserResponse, UserRole
from .generator import generate_map_from_image, get_supported_crs
from .overpass import query_osm_features

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mapgen", tags=["mapgen"])

FIWARE_ORION_URL = os.getenv("FIWARE_ORION_URL", "http://localhost:1026/v2/entities")
FIWARE_SERVICE = os.getenv("FIWARE_SERVICE", "smartrobotics")
FIWARE_SERVICE_PATH = os.getenv("FIWARE_SERVICE_PATH", "/")

FIWARE_HEADERS = {
    "Content-Type": "application/json",
    "fiware-service": FIWARE_SERVICE,
    "fiware-servicepath": FIWARE_SERVICE_PATH,
}


@router.get("/crs-list")
async def crs_list(_user: UserResponse = Depends(get_current_user)):
    return get_supported_crs()


@router.post("/generate")
async def generate_map(
    data: dict = Body(...),
    user: UserResponse = Depends(require_role(UserRole.admin, UserRole.operator)),
):
    """
    Generate map from drawn occupancy grid.

    Body: { name, resolution, origin: [x, y, 0], imageData: "<base64 PNG>",
            zones: [{ name, zoneType, polygon, goalPoint?, isDefault?, speedLimit? }] }
    """
    name = data.get("name")
    resolution = data.get("resolution", 0.1)
    origin = data.get("origin", [0, 0, 0])
    image_data = data.get("imageData")
    zones = data.get("zones", [])

    if not name:
        raise HTTPException(status_code=400, detail="Map name is required")
    if not image_data:
        raise HTTPException(status_code=400, detail="imageData (base64 PNG) is required")

    try:
        result = generate_map_from_image(name, float(resolution), origin, image_data)
    except Exception as e:
        logger.error(f"Map generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Map generation failed: {e}")

    # Create zones in FIWARE if provided
    map_id = result.get("mapId", name)
    created_zones = []
    for zone_data in zones:
        try:
            zone_id = str(uuid.uuid4())[:8]
            now = datetime.now(timezone.utc).isoformat()
            zone_type = zone_data.get("zoneType", "parking")
            polygon = zone_data.get("polygon", [])
            goal_point = zone_data.get("goalPoint")
            is_default = zone_data.get("isDefault", False)
            speed_limit = zone_data.get("speedLimit")

            if len(polygon) < 3:
                continue

            # Compute centroid if no goalPoint for parking
            if zone_type == "parking" and not goal_point:
                n = len(polygon)
                goal_point = [sum(p[0] for p in polygon) / n, sum(p[1] for p in polygon) / n]

            # If this zone is default, clear other defaults
            if is_default:
                try:
                    params = {"type": "Zone", "q": f"mapId=={map_id};isDefault=='true'", "limit": "1000"}
                    read_headers = {"Accept": "application/json", "fiware-service": FIWARE_SERVICE, "fiware-servicepath": FIWARE_SERVICE_PATH}
                    async with httpx.AsyncClient() as client:
                        res = await client.get(FIWARE_ORION_URL, params=params, headers=read_headers, timeout=10.0)
                        if res.status_code == 200:
                            for entity in res.json():
                                eid = entity.get("id", "")
                                url = f"{FIWARE_ORION_URL}/{eid}/attrs"
                                await client.patch(url, json={"isDefault": {"type": "Text", "value": "false"}}, headers=FIWARE_HEADERS, timeout=10.0)
                except Exception as e:
                    logger.warning(f"Error clearing defaults: {e}")

            entity = {
                "id": f"urn:ngsi-ld:Zone:{zone_id}",
                "type": "Zone",
                "mapId": {"type": "Text", "value": map_id},
                "name": {"type": "Text", "value": zone_data.get("name", f"Zone {zone_id}")},
                "zoneType": {"type": "Text", "value": zone_type},
                "polygon": {"type": "Text", "value": json.dumps(polygon)},
                "speedLimit": {"type": "Number", "value": speed_limit or 0},
                "color": {"type": "Text", "value": "#3b82f640" if zone_type == "parking" else "#f59e0b40"},
                "goalPoint": {"type": "Text", "value": json.dumps(goal_point) if goal_point else ""},
                "isDefault": {"type": "Text", "value": "true" if is_default else "false"},
                "createdBy": {"type": "Text", "value": user.username},
                "createdAt": {"type": "Text", "value": now},
            }

            async with httpx.AsyncClient() as client:
                res = await client.post(FIWARE_ORION_URL, json=entity, headers=FIWARE_HEADERS, timeout=10.0)
                if res.status_code in (201, 204):
                    created_zones.append({"zoneId": zone_id, "name": zone_data.get("name", "")})
                else:
                    logger.warning(f"Failed to create zone {zone_id}: {res.text}")
        except Exception as e:
            logger.error(f"Error creating zone: {e}")

    result["zones"] = created_zones
    return result


@router.post("/overpass")
async def overpass_proxy(
    data: dict = Body(...),
    _user: UserResponse = Depends(get_current_user),
):
    """
    Query Overpass API for OSM features within a bounding box.
    Classifies features as occupied/free/unknown for occupancy grid generation.

    Body: { south, west, north, east } (WGS84 coordinates)
    """
    south = data.get("south")
    west = data.get("west")
    north = data.get("north")
    east = data.get("east")

    if None in (south, west, north, east):
        raise HTTPException(status_code=400, detail="south, west, north, east are required")

    # Limit bbox size (~2km max dimension)
    if abs(north - south) > 0.025 or abs(east - west) > 0.04:
        raise HTTPException(
            status_code=400,
            detail="Bounding box too large for OSM query. Max ~2km x 2km.",
        )

    try:
        result = await query_osm_features(
            float(south), float(west), float(north), float(east)
        )
        return result
    except Exception as e:
        logger.error(f"Overpass query failed: {e}")
        raise HTTPException(status_code=502, detail=f"Overpass API error: {e}")
