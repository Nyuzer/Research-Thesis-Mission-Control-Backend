from __future__ import annotations
from typing import Optional
import asyncio
import httpx
import logging
import json

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


async def query_osm_features(south: float, west: float, north: float, east: float) -> dict:
    """
    Query Overpass API for buildings, roads, water, etc. within bounding box.
    Returns GeoJSON-like feature collection with occupancy classification.
    """
    bbox = f"{south},{west},{north},{east}"

    query = (
        f'[out:json][timeout:45][bbox:{bbox}];'
        f'(way["building"];relation["building"];'
        f'way["highway"~"^(motorway|trunk|primary|secondary|tertiary|residential|service|unclassified|pedestrian|footway|cycleway|path|living_street)$"];'
        f'way["waterway"];way["natural"="water"];relation["natural"="water"];'
        f'way["landuse"="industrial"];way["landuse"="commercial"];way["amenity"="parking"];'
        f');out geom;'
    )

    logger.info(f"Overpass query bbox={bbox}")

    for attempt in range(2):
        try:
            async with httpx.AsyncClient(verify=False) as client:
                resp = await client.post(
                    OVERPASS_URL,
                    data={"data": query},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=90.0,
                )
                logger.info(f"Overpass response status: {resp.status_code}")
                if resp.status_code in (429, 504) and attempt == 0:
                    logger.warning(f"Overpass returned {resp.status_code}, retrying once in 10s")
                    await asyncio.sleep(10)
                    continue
                resp.raise_for_status()
                data = resp.json()
                break
        except httpx.ConnectError as e:
            logger.error(f"Cannot connect to Overpass API: {e}")
            raise RuntimeError(f"Cannot connect to Overpass API: {e}")
        except httpx.HTTPStatusError as e:
            logger.error(f"Overpass API returned {e.response.status_code}: {e.response.text[:200]}")
            raise RuntimeError(f"Overpass API error {e.response.status_code}")
        except Exception as e:
            logger.error(f"Overpass request failed: {type(e).__name__}: {e}")
            raise
    else:
        raise RuntimeError("Overpass API unavailable (504). Please try again.")

    features = []
    for element in data.get("elements", []):
        geom = _element_to_geojson(element)
        if geom is None:
            continue

        tags = element.get("tags", {})
        occupancy = _classify(tags)

        props = {
            "occupancy": occupancy,
            "osm_type": _tag_type(tags),
        }
        # Include road width (meters) for LineString road features
        highway = tags.get("highway")
        if highway and geom.get("type") == "LineString":
            props["width"] = _ROAD_WIDTH.get(highway, 4)

        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": props,
        })

    logger.info(f"Overpass returned {len(features)} classified features for bbox {bbox}")
    return {"type": "FeatureCollection", "features": features}


_ROAD_WIDTH: dict = {
    "motorway": 16,
    "trunk": 14,
    "primary": 12,
    "secondary": 10,
    "tertiary": 8,
    "residential": 6,
    "service": 4,
    "unclassified": 6,
    "living_street": 5,
    "pedestrian": 4,
    "footway": 2,
    "cycleway": 2,
    "path": 1.5,
}


def _element_to_geojson(el: dict) -> Optional[dict]:
    """Convert Overpass element to GeoJSON geometry.

    Roads (highway=*) are returned as LineString with a width property
    so the frontend can render them as buffered strokes rather than
    broken polygons.
    """
    tags = el.get("tags", {})
    is_road = bool(tags.get("highway"))

    if el.get("type") == "way" and "geometry" in el:
        coords = [[n["lon"], n["lat"]] for n in el["geometry"]]

        if is_road:
            # Roads are lines, not areas – return as LineString
            if len(coords) < 2:
                return None
            return {"type": "LineString", "coordinates": coords}

        # Area features: polygon
        if len(coords) < 3:
            return None
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        return {"type": "Polygon", "coordinates": [coords]}

    if el.get("type") == "relation" and "members" in el:
        for member in el["members"]:
            if member.get("role") == "outer" and "geometry" in member:
                coords = [[n["lon"], n["lat"]] for n in member["geometry"]]
                if len(coords) >= 3:
                    if coords[0] != coords[-1]:
                        coords.append(coords[0])
                    return {"type": "Polygon", "coordinates": [coords]}
    return None


def _classify(tags: dict) -> str:
    """Classify OSM tags into occupancy type."""
    if tags.get("building"):
        return "occupied"
    if tags.get("natural") == "water" or tags.get("waterway"):
        return "occupied"
    if tags.get("landuse") in ("industrial", "commercial"):
        return "occupied"
    if tags.get("highway"):
        return "free"
    if tags.get("amenity") == "parking":
        return "occupied"
    return "unknown"


def _tag_type(tags: dict) -> str:
    if tags.get("building"):
        return "building"
    if tags.get("highway"):
        return f"road:{tags['highway']}"
    if tags.get("waterway") or tags.get("natural") == "water":
        return "water"
    if tags.get("amenity") == "parking":
        return "parking"
    if tags.get("landuse"):
        return f"landuse:{tags['landuse']}"
    return "other"
