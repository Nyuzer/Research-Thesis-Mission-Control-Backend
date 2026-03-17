import base64
import os
import uuid
import yaml
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

MAPS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "maps")


def generate_map_from_image(
    name: str,
    resolution: float,
    origin: list,
    image_data_b64: str,
) -> dict:
    """
    Generate map from base64 PNG occupancy grid image.

    Returns dict with mapId and map info.
    """
    map_id = f"gen_{uuid.uuid4().hex[:8]}"
    map_dir = os.path.join(MAPS_DIR, map_id)
    os.makedirs(map_dir, exist_ok=True)

    # Decode and save PNG
    image_bytes = base64.b64decode(image_data_b64)
    image_path = os.path.join(map_dir, "map.png")
    with open(image_path, "wb") as f:
        f.write(image_bytes)

    # Generate map.yaml
    yaml_data = {
        "image": "map.png",
        "resolution": resolution,
        "origin": origin if len(origin) >= 3 else [origin[0], origin[1], 0.0],
        "negate": 0,
        "occupied_thresh": 0.65,
        "free_thresh": 0.196,
    }
    yaml_path = os.path.join(map_dir, "map.yaml")
    with open(yaml_path, "w") as f:
        yaml.dump(yaml_data, f, default_flow_style=False)

    logger.info(f"Generated map '{name}' at {map_dir}")

    return {
        "mapId": map_id,
        "name": name,
        "resolution": resolution,
        "origin": yaml_data["origin"],
        "yamlPath": yaml_path,
        "imagePath": image_path,
    }


def get_supported_crs() -> list:
    """Return list of supported CRS codes."""
    return [
        {"code": "EPSG:25832", "name": "UTM Zone 32N (Germany)", "proj4": "+proj=utm +zone=32 +ellps=GRS80 +units=m +no_defs"},
        {"code": "EPSG:25833", "name": "UTM Zone 33N", "proj4": "+proj=utm +zone=33 +ellps=GRS80 +units=m +no_defs"},
        {"code": "EPSG:4326", "name": "WGS84 (lat/lon)", "proj4": "+proj=longlat +datum=WGS84 +no_defs"},
        {"code": "EPSG:3857", "name": "Web Mercator", "proj4": "+proj=merc +a=6378137 +b=6378137 +lat_ts=0 +lon_0=0 +x_0=0 +y_0=0 +k=1 +units=m +no_defs"},
    ]
