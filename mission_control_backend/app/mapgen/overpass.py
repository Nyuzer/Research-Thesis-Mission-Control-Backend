from __future__ import annotations
from typing import Optional
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
        f'[out:json][timeout:30][bbox:{bbox}];'
        f'(way["building"];relation["building"];'
        f'way["highway"~"^(motorway|trunk|primary|secondary|tertiary|residential|service|unclassified|pedestrian|footway|cycleway|path|living_street)$"];'
        f'way["waterway"];way["natural"="water"];relation["natural"="water"];'
        f'way["landuse"="industrial"];way["landuse"="commercial"];way["amenity"="parking"];'
        f');out geom;'
    )

    logger.info(f"Overpass query for bbox {bbox}: {query[:100]}...")
    try:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                OVERPASS_URL,
                data={"data": query},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=60.0,
            )
            logger.info(f"Overpass response status: {resp.status_code}")
            resp.raise_for_status()
            data = resp.json()
    except httpx.ConnectError as e:
        logger.error(f"Cannot connect to Overpass API: {e}")
        raise RuntimeError(f"Cannot connect to Overpass API: {e}")
    except httpx.HTTPStatusError as e:
        logger.error(f"Overpass API returned {e.response.status_code}: {e.response.text[:200]}")
        raise RuntimeError(f"Overpass API error {e.response.status_code}")
    except Exception as e:
        logger.error(f"Overpass request failed: {type(e).__name__}: {e}")
        raise

    features = []
    for element in data.get("elements", []):
        geom = _element_to_geojson(element)
        if geom is None:
            continue

        tags = element.get("tags", {})
        occupancy = _classify(tags)

        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "occupancy": occupancy,
                "osm_type": _tag_type(tags),
            },
        })

    logger.info(f"Overpass returned {len(features)} classified features for bbox {bbox}")
    return {"type": "FeatureCollection", "features": features}


def _element_to_geojson(el: dict) -> Optional[dict]:
    """Convert Overpass element to GeoJSON geometry."""
    if el.get("type") == "way" and "geometry" in el:
        coords = [[n["lon"], n["lat"]] for n in el["geometry"]]
        if len(coords) < 3:
            return None
        # Close ring if not closed
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        return {"type": "Polygon", "coordinates": [coords]}

    if el.get("type") == "relation" and "members" in el:
        # Take the first outer way with geometry
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
        return "parking"
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
