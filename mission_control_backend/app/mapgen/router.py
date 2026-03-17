from fastapi import APIRouter, HTTPException, Depends, Body
import logging

from app.auth.dependencies import get_current_user, require_role
from app.auth.models import UserResponse, UserRole
from .generator import generate_map_from_image, get_supported_crs
from .overpass import query_osm_features

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mapgen", tags=["mapgen"])


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

    Body: { name, resolution, origin: [x, y, 0], imageData: "<base64 PNG>" }
    """
    name = data.get("name")
    resolution = data.get("resolution", 0.05)
    origin = data.get("origin", [0, 0, 0])
    image_data = data.get("imageData")

    if not name:
        raise HTTPException(status_code=400, detail="Map name is required")
    if not image_data:
        raise HTTPException(status_code=400, detail="imageData (base64 PNG) is required")

    try:
        result = generate_map_from_image(name, float(resolution), origin, image_data)
        return result
    except Exception as e:
        logger.error(f"Map generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Map generation failed: {e}")


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
