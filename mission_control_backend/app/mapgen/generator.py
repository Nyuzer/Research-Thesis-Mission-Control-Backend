import base64
import io
import os
import uuid
import yaml
import logging
from datetime import datetime, timezone

import numpy as np
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)

MAPS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "maps")

# Zone colors from the frontend canvas (RGB, tolerance ±20)
# Each entry: (R, G, B, target_grayscale)
#   254 = FREE   (occ = 0.004, below free_thresh 0.196)
#   0   = OCCUPIED (occ = 1.0, above occupied_thresh 0.65)
#   205 = UNKNOWN  (occ = 0.196, at threshold boundary → NOT free)
_ZONE_COLORS = [
    # Roads: near-white (254,254,254)
    ((254, 254, 254), 20, 254),
    # Parking zones: blue (59,130,246)
    ((59, 130, 246), 20, 254),
    # Speed limit zones: orange (245,158,11)
    ((245, 158, 11), 20, 254),
    # Buildings: black (0,0,0)
    ((0, 0, 0), 15, 0),
]

# Default grayscale for unrecognized pixels (unknown/safe)
_DEFAULT_GRAY = 205


def _convert_rgba_to_costmap_grayscale(image_bytes):
    """
    Convert color RGBA PNG from canvas to single-channel grayscale PNG
    suitable for map_server with negate=0 and trinary mode.

    Color mapping:
      Roads (white)     → 254 (FREE)
      Parking (blue)    → 254 (FREE)
      Speed limit (orange) → 254 (FREE)
      Buildings (black) → 0   (OCCUPIED)
      Unknown/other     → 205 (UNKNOWN)
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    pixels = np.array(img)
    rgb = pixels[:, :, :3]

    # Start with all pixels as unknown
    gray = np.full((pixels.shape[0], pixels.shape[1]), _DEFAULT_GRAY, dtype=np.uint8)

    for (r, g, b), tolerance, target in _ZONE_COLORS:
        mask = (
            (np.abs(rgb[:, :, 0].astype(np.int16) - r) <= tolerance)
            & (np.abs(rgb[:, :, 1].astype(np.int16) - g) <= tolerance)
            & (np.abs(rgb[:, :, 2].astype(np.int16) - b) <= tolerance)
        )
        gray[mask] = target

    # Dilate FREE pixels by 1px to cover anti-aliased edges between zones.
    # Canvas 2D anti-aliasing blends adjacent polygon colors, creating pixels
    # that don't match any zone color → default to UNKNOWN (205) → impassable.
    # MaxFilter(3) = morphological dilation with 3x3 kernel.
    # Only overwrite UNKNOWN pixels so building edges (0) are preserved.
    free_mask_img = Image.fromarray((gray == 254).astype(np.uint8) * 255, mode="L")
    dilated = np.array(free_mask_img.filter(ImageFilter.MaxFilter(3))) > 0
    gray[dilated & (gray == _DEFAULT_GRAY)] = 254

    result = Image.fromarray(gray, mode="L")
    buf = io.BytesIO()
    result.save(buf, format="PNG")
    return buf.getvalue()


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

    # Decode base64 → convert RGBA to costmap grayscale → save
    raw_bytes = base64.b64decode(image_data_b64)
    grayscale_bytes = _convert_rgba_to_costmap_grayscale(raw_bytes)
    image_path = os.path.join(map_dir, "map.png")
    with open(image_path, "wb") as f:
        f.write(grayscale_bytes)

    # Generate map.yaml (negate=0 for correct costmap interpretation)
    yaml_data = {
        "image": "map.png",
        "name": name,
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
