from fastapi import FastAPI, HTTPException, File, UploadFile, Body, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from typing import List, Optional, Tuple
from contextlib import asynccontextmanager
import asyncio
import httpx
import uuid
import os
import yaml
import shutil
from datetime import datetime, timedelta
import logging
import json
import paho.mqtt.client as mqtt
from threading import Lock
import pyproj
import time
from dateutil import parser as date_parser
import pytz

# APScheduler imports
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.triggers.cron import CronTrigger

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    start_scheduler()
    # Start WS broadcast loop
    global ws_broadcast_task
    ws_broadcast_task = asyncio.create_task(ws_broadcast_loop())
    yield
    # Shutdown
    stop_scheduler()
    # Stop WS loop
    if ws_broadcast_task:
        ws_broadcast_task.cancel()
        try:
            await ws_broadcast_task
        except Exception:
            pass

app = FastAPI(title="Mission Control Backend", version="1.0.0", lifespan=lifespan)

# CORS middleware for web UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# FIWARE Configuration
FIWARE_IOT_AGENT_URL = os.getenv("FIWARE_IOT_AGENT_URL", "http://localhost:4041/v2/op/update")
FIWARE_ORION_URL = os.getenv("FIWARE_ORION_URL", "http://localhost:1026/v2/entities")
FIWARE_SERVICE = os.getenv("FIWARE_SERVICE", "smartrobotics")
FIWARE_SERVICE_PATH = os.getenv("FIWARE_SERVICE_PATH", "/")

# MQTT Configuration
MQTT_MODE = os.getenv("MQTT_MODE", "fiware")  # "fiware" or "local"
LOCAL_MQTT_HOST = os.getenv("LOCAL_MQTT_HOST", "localhost")
LOCAL_MQTT_PORT = int(os.getenv("LOCAL_MQTT_PORT", "1883"))
LOCAL_MQTT_USERNAME = os.getenv("LOCAL_MQTT_USERNAME", "")
LOCAL_MQTT_PASSWORD = os.getenv("LOCAL_MQTT_PASSWORD", "")

# Local Mission Storage (for local MQTT mode)
local_missions = {}
local_missions_lock = Lock()

# In-memory scheduled mission store (to be replaced with persistent storage)
scheduled_missions = []  # List[ScheduledMission]
scheduled_missions_lock = Lock()

# Map operations locking mechanism
maps_lock = Lock()
map_locks = {}

# APScheduler configuration
jobstores = {
    'default': MongoDBJobStore(
        database='orion',
        collection='scheduled_jobs',
        host='localhost',
        port=27017
    )
}

executors = {
    'default': AsyncIOExecutor()
}

scheduler = AsyncIOScheduler(
    jobstores=jobstores,
    executors=executors,
    timezone='Europe/Berlin'
)

# Legacy scheduler variables (for backward compatibility)
scheduler_running = False
scheduler_thread = None

# WebSocket connections store
connected_websockets: List[WebSocket] = []
ws_broadcast_task: Optional[asyncio.Task] = None


# Data Models
class Point(BaseModel):
    type: str = "Point"
    coordinates: List[float]  # [x, y, z]

class CommandMessage(BaseModel):
    command: str = "MOVE_TO"
    commandTime: str
    waypoints: Point
    mapId: str
    missionId: Optional[str] = None

class MissionRequest(BaseModel):
    robotId: str
    destination: Point
    mapId: str

class MissionStatusUpdate(BaseModel):
    status: str  # e.g., "in_progress", "completed", "failed", "cancelled"
    robotPosition: Optional[Point] = None
    completedTime: Optional[str] = None
    executedTime: Optional[str] = None
    sentTime: Optional[str] = None
    errorMessage: Optional[str] = None

class MapInfo(BaseModel):
    mapId: str
    name: str
    resolution: float
    width: int
    height: int
    origin: List[float]
    uploadTime: str

class Mission(BaseModel):
    robotId: str
    command: CommandMessage
    status: str
    completedTime: Optional[str] = None
    executedTime: Optional[str] = None
    sentTime: str
    fiwareResponse: Optional[dict] = None
    developmentMode: bool = False

class ScheduledMission(BaseModel):
    robotId: str
    command: CommandMessage      # CommandMessage structure
    scheduledTime: Optional[str] = None  # ISO8601, CET/CEST (German time) - for one-time missions
    cron: Optional[str] = None  # Cron expression for recurring missions
    scheduleType: str = "once"  # "once" or "recurring"
    estimatedDuration: Optional[int] = None  # In seconds, for conflict detection
    status: str  # e.g., "scheduled", "in_progress", "completed", "failed", "cancelled", "expired"
    sentTime: Optional[str] = None  # When the mission was actually sent to the robot
    executedTime: Optional[str] = None  # When execution started
    completedTime: Optional[str] = None  # When execution finished
    errorMessage: Optional[str] = None
    maxRetries: int = 3
    retryCount: int = 0
    lastError: Optional[str] = None

class MissionScheduledRequest(BaseModel):
    robotId: str
    destination: Point
    mapId: str
    scheduledTime: Optional[str] = None  # ISO8601 format for one-time missions
    cron: Optional[str] = None  # Cron expression for recurring missions

class RobotInfo(BaseModel):
    robotId: str
    name: Optional[str] = None
    online: bool = False
    batteryPct: Optional[float] = None
    state: Optional[str] = None
    lastSeen: Optional[str] = None
    currentMissionId: Optional[str] = None
    # Position in EPSG:25832 meters for map overlay
    position25832: Optional[Tuple[float, float]] = None

def validate_scheduling_input(scheduled_time: Optional[str], cron: Optional[str]) -> Tuple[str, str]:
    """
    Validate scheduling input and return schedule type and value.
    Returns: (schedule_type, schedule_value)
    """
    if scheduled_time and cron:
        raise HTTPException(
            status_code=400, 
            detail="Incorrect Input - can be cron or scheduledTime, not both at the same time"
        )
    
    if not scheduled_time and not cron:
        raise HTTPException(
            status_code=400, 
            detail="Either cron or scheduledTime must be provided"
        )
    
    if scheduled_time:
        # Validate ISO8601 format
        try:
            dt = date_parser.isoparse(scheduled_time)
            if dt.tzinfo is None:
                berlin = pytz.timezone("Europe/Berlin")
                dt = berlin.localize(dt)
            return "once", dt.isoformat()
        except Exception as e:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid scheduledTime format: {e}"
            )
    
    if cron:
        # Validate cron expression
        try:
            # First check if it's a valid cron format
            parts = cron.split()
            if len(parts) != 5:
                raise ValueError(f"Invalid cron format. Expected 5 parts (minute hour day month day_of_week), got {len(parts)} parts")
            
            # Validate with APScheduler
            CronTrigger.from_crontab(cron)
            
            # Additional validation for common issues
            minute, hour, day, month, day_of_week = parts
            
            # Check for reasonable values
            if minute == "*/1" and hour == "*" and day == "*" and month == "*" and day_of_week == "*":
                logger.warning(f"Cron expression '{cron}' will execute every minute - this may be very frequent")
            
            return "recurring", cron
        except Exception as e:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid cron expression '{cron}': {e}. Expected format: minute hour day month day_of_week (e.g., '0 9 * * *' for daily at 9 AM, '*/5 * * * *' for every 5 minutes)"
            )

async def check_scheduled_mission_conflict(new_mission: ScheduledMission) -> Optional[str]:
    """
    Check for scheduling conflicts for the same robot.
    Handles both one-time and recurring missions.
    Returns None if no conflict, or a string describing the conflict if found.
    """
    try:
        # Get all existing missions for this robot from Orion
        existing_missions = await list_scheduled_missions_from_orion()
        robot_missions = [m for m in existing_missions if m.robotId == new_mission.robotId]
        
        # Filter out completed/cancelled/failed missions
        active_missions = [m for m in robot_missions if m.status not in ("completed", "cancelled", "failed", "expired")]
        
        for existing_mission in active_missions:
            conflict_reason = _check_mission_conflict(new_mission, existing_mission)
            if conflict_reason:
                return conflict_reason
        
        return None
        
    except Exception as e:
        logger.error(f"Error checking mission conflicts: {e}")
        return f"Error checking conflicts: {e}"

def _check_mission_conflict(new_mission: ScheduledMission, existing_mission: ScheduledMission) -> Optional[str]:
    """
    Check if two missions conflict with each other.
    Returns conflict description if found, None otherwise.
    """
    # Case 1: Both are one-time missions
    if new_mission.scheduleType == "once" and existing_mission.scheduleType == "once":
        return _check_one_time_conflict(new_mission, existing_mission)
    
    # Case 2: Both are recurring missions
    elif new_mission.scheduleType == "recurring" and existing_mission.scheduleType == "recurring":
        return _check_recurring_conflict(new_mission, existing_mission)
    
    # Case 3: Mixed types (one-time vs recurring)
    else:
        return _check_mixed_conflict(new_mission, existing_mission)

def _check_one_time_conflict(new_mission: ScheduledMission, existing_mission: ScheduledMission) -> Optional[str]:
    """Check conflict between two one-time missions"""
    if not new_mission.scheduledTime or not existing_mission.scheduledTime:
        return None
    
    from dateutil import parser as date_parser
    import pytz
    
    # Parse scheduled times
    new_start = date_parser.isoparse(new_mission.scheduledTime)
    existing_start = date_parser.isoparse(existing_mission.scheduledTime)
    
    # Add timezone if missing
    if new_start.tzinfo is None:
        berlin = pytz.timezone("Europe/Berlin")
        new_start = berlin.localize(new_start)
    if existing_start.tzinfo is None:
        berlin = pytz.timezone("Europe/Berlin")
        existing_start = berlin.localize(existing_start)
    
    # Calculate end times
    new_duration = new_mission.estimatedDuration or 300  # Default 5 minutes
    existing_duration = existing_mission.estimatedDuration or 300
    
    new_end = new_start + timedelta(seconds=new_duration)
    existing_end = existing_start + timedelta(seconds=existing_duration)
    
    # Check for overlap
    if (new_start < existing_end) and (new_end > existing_start):
        return f"Conflict: One-time mission overlaps with existing mission {existing_mission.command.missionId} scheduled from {existing_mission.scheduledTime} for robot {new_mission.robotId}."
    
    return None

def _check_recurring_conflict(new_mission: ScheduledMission, existing_mission: ScheduledMission) -> Optional[str]:
    """Check conflict between two recurring missions"""
    if not new_mission.cron or not existing_mission.cron:
        return None
    
    # Special case: If either mission runs every minute (*/1 * * * *), they will always conflict
    if new_mission.cron == "*/1 * * * *" or existing_mission.cron == "*/1 * * * *":
        return f"Conflict: Cannot create recurring mission with cron '{new_mission.cron}' because robot {new_mission.robotId} already has a recurring mission with cron '{existing_mission.cron}' that runs every minute. Every-minute missions conflict with all other recurring missions."
    
    # Check for other frequent patterns that would likely conflict
    frequent_patterns = [
        "*/1 * * * *",  # Every minute
        "*/2 * * * *",  # Every 2 minutes
        "*/3 * * * *",  # Every 3 minutes
        "*/5 * * * *",  # Every 5 minutes
        "*/10 * * * *", # Every 10 minutes
        "*/15 * * * *", # Every 15 minutes
    ]
    
    new_is_frequent = new_mission.cron in frequent_patterns
    existing_is_frequent = existing_mission.cron in frequent_patterns
    
    # If both are frequent, they likely conflict
    if new_is_frequent and existing_is_frequent:
        return f"Conflict: Cannot create recurring mission with cron '{new_mission.cron}' because robot {new_mission.robotId} already has a frequent recurring mission with cron '{existing_mission.cron}'. Frequent recurring missions may overlap."
    
    # For less frequent patterns, we could do more sophisticated analysis
    # For now, we'll be conservative and warn about potential conflicts
    if new_is_frequent or existing_is_frequent:
        return f"Warning: Potential conflict between recurring mission with cron '{new_mission.cron}' and existing mission with cron '{existing_mission.cron}' for robot {new_mission.robotId}. One of these is a frequent pattern that may cause overlaps."
    
    # For non-frequent patterns, we assume they don't conflict
    # This could be enhanced with more sophisticated cron analysis in the future
    return None

def _check_mixed_conflict(new_mission: ScheduledMission, existing_mission: ScheduledMission) -> Optional[str]:
    """Check conflict between one-time and recurring missions"""
    # For mixed types, we need to be more careful
    # A recurring mission could potentially conflict with a one-time mission
    
    if new_mission.scheduleType == "recurring" and existing_mission.scheduleType == "once":
        # New is recurring, existing is one-time
        return _check_recurring_vs_one_time_conflict(new_mission, existing_mission)
    else:
        # New is one-time, existing is recurring
        return _check_recurring_vs_one_time_conflict(existing_mission, new_mission)

def _check_recurring_vs_one_time_conflict(recurring_mission: ScheduledMission, one_time_mission: ScheduledMission) -> Optional[str]:
    """Check if a recurring mission conflicts with a one-time mission"""
    if not recurring_mission.cron or not one_time_mission.scheduledTime:
        return None
    
    # If the recurring mission runs every minute, it will definitely conflict
    if recurring_mission.cron == "*/1 * * * *":
        return f"Conflict: Cannot create recurring mission with cron '{recurring_mission.cron}' because robot {recurring_mission.robotId} already has a one-time mission scheduled for {one_time_mission.scheduledTime}. Every-minute recurring missions conflict with all other missions."
    
    # For other recurring patterns, we could do more sophisticated analysis
    # For now, we'll warn about potential conflicts with frequent patterns
    frequent_patterns = [
        "*/2 * * * *",  # Every 2 minutes
        "*/3 * * * *",  # Every 3 minutes
        "*/5 * * * *",  # Every 5 minutes
    ]
    
    if recurring_mission.cron in frequent_patterns:
        return f"Warning: Potential conflict between recurring mission with cron '{recurring_mission.cron}' and one-time mission scheduled for {one_time_mission.scheduledTime} for robot {recurring_mission.robotId}. Frequent recurring missions may overlap with one-time missions."
    
    # For less frequent patterns, we assume no conflict
    return None

# Coordinate Transformation System
# EPSG:25832 = UTM Zone 32N (German coordinate system)
# EPSG:4326 = WGS84 (World Geodetic System - latitude/longitude)

# Initialize coordinate transformers
try:
    epsg_25832 = pyproj.CRS('EPSG:25832')  # UTM Zone 32N
    wgs84 = pyproj.CRS('EPSG:4326')        # WGS84 lat/lon
    
    # Create transformers for bidirectional conversion
    epsg_to_wgs84_transformer = pyproj.Transformer.from_crs(epsg_25832, wgs84, always_xy=True)
    wgs84_to_epsg_transformer = pyproj.Transformer.from_crs(wgs84, epsg_25832, always_xy=True)
    
    logger.info("✅ Coordinate transformation system initialized successfully")
    logger.info(f"   EPSG:25832 (UTM Zone 32N) ↔ WGS84 (lat/lon)")
    
except Exception as e:
    logger.error(f"❌ Failed to initialize coordinate transformation system: {str(e)}")
    epsg_to_wgs84_transformer = None
    wgs84_to_epsg_transformer = None

def transform_epsg_to_wgs84(x_utm, y_utm):
    """
    Transform coordinates from EPSG:25832 (UTM Zone 32N) to WGS84 (lat/lon)
    
    Args:
        x_utm (float): X coordinate in UTM Zone 32N (meters)
        y_utm (float): Y coordinate in UTM Zone 32N (meters)
    
    Returns:
        tuple: (longitude, latitude) in WGS84 degrees
    
    Raises:
        HTTPException: If coordinate transformation fails
    """
    try:
        if epsg_to_wgs84_transformer is None:
            raise HTTPException(
                status_code=500, 
                detail="Coordinate transformation system not available"
            )
        
        # Transform using pyproj (always_xy=True means input is (x, y) not (lat, lon))
        lon, lat = epsg_to_wgs84_transformer.transform(x_utm, y_utm)
        
        # Validate reasonable coordinate ranges
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError(f"Invalid WGS84 coordinates: lon={lon}, lat={lat}")
        
        logger.debug(f"🔄 Coordinate transform: UTM({x_utm}, {y_utm}) → WGS84({lat:.6f}, {lon:.6f})")
        return lon, lat
        
    except Exception as e:
        logger.error(f"❌ Coordinate transformation failed: UTM({x_utm}, {y_utm}) - {str(e)}")
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid coordinates for transformation: {str(e)}"
        )

def transform_wgs84_to_epsg(lat, lon):
    """
    Transform coordinates from WGS84 (lat/lon) to EPSG:25832 (UTM Zone 32N)
    
    Args:
        lat (float): Latitude in WGS84 degrees
        lon (float): Longitude in WGS84 degrees
    
    Returns:
        tuple: (x_utm, y_utm) in UTM Zone 32N meters
    
    Raises:
        HTTPException: If coordinate transformation fails
    """
    try:
        if wgs84_to_epsg_transformer is None:
            raise HTTPException(
                status_code=500, 
                detail="Coordinate transformation system not available"
            )
        
        # Validate input ranges
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError(f"Invalid WGS84 coordinates: lat={lat}, lon={lon}")
        
        # Transform using pyproj (input as lon, lat due to always_xy=True)
        x_utm, y_utm = wgs84_to_epsg_transformer.transform(lon, lat)
        
        logger.debug(f"🔄 Coordinate transform: WGS84({lat:.6f}, {lon:.6f}) → UTM({x_utm:.3f}, {y_utm:.3f})")
        return x_utm, y_utm
        
    except Exception as e:
        logger.error(f"❌ Coordinate transformation failed: WGS84({lat}, {lon}) - {str(e)}")
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid coordinates for transformation: {str(e)}"
        )

def create_geojson_point(x_utm, y_utm):
    """
    Create GeoJSON Point from UTM coordinates (transforms to WGS84)
    
    Args:
        x_utm (float): X coordinate in UTM Zone 32N
        y_utm (float): Y coordinate in UTM Zone 32N
    
    Returns:
        dict: GeoJSON Point with WGS84 coordinates
    """
    lon, lat = transform_epsg_to_wgs84(x_utm, y_utm)
    return {
        "type": "Point",
        "coordinates": [lon, lat]  # GeoJSON format: [longitude, latitude]
    }

async def list_robots_from_orion() -> List[RobotInfo]:
    """List Robot entities from FIWARE Orion and map to RobotInfo.
    Expects attributes: pose (geo:json lon/lat), battery (Number), robotState (Text).
    """
    params = {
        "type": "Robot",
        "limit": "1000"
    }
    headers = {
        "Accept": "application/json",
        "fiware-service": FIWARE_SERVICE,
        "fiware-servicepath": FIWARE_SERVICE_PATH
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                FIWARE_ORION_URL,
                params=params,
                headers=headers,
                timeout=10.0
            )
            response.raise_for_status()
            entities = response.json()
            robots_parsed: List[RobotInfo] = []
            for entity in entities:
                try:
                    robot_id_full = entity.get("id", "")
                    robot_id = robot_id_full.replace("urn:ngsi-ld:Robot:", "") if robot_id_full else "unknown"

                    def safe_get_value_local(e, name, default=None):
                        field = e.get(name, {})
                        if isinstance(field, dict):
                            return field.get("value", default)
                        return default

                    name = safe_get_value_local(entity, "name", robot_id)
                    battery = safe_get_value_local(entity, "battery", None)
                    robot_state = safe_get_value_local(entity, "robotState", "Unknown")
                    # Derive online flag from robotState not being 'ERROR' or missing; simplistic heuristic
                    online = robot_state not in (None, "Unknown")
                    last_seen = safe_get_value_local(entity, "TimeInstant", None)
                    current_mission_id = safe_get_value_local(entity, "currentMissionId", None)

                    # Position: pose as GeoJSON lon/lat → convert to EPSG:25832
                    pose = safe_get_value_local(entity, "pose", None)
                    pos_25832 = None
                    try:
                        if isinstance(pose, dict) and pose.get("type") == "Point":
                            coords = pose.get("coordinates", [])
                            if len(coords) >= 2:
                                lon, lat = coords[0], coords[1]
                                x_utm, y_utm = transform_wgs84_to_epsg(lat, lon)
                                pos_25832 = (x_utm, y_utm)
                    except Exception:
                        pos_25832 = None

                    robots_parsed.append(RobotInfo(
                        robotId=robot_id,
                        name=name,
                        online=online,
                        batteryPct=battery,
                        state=robot_state,
                        lastSeen=last_seen,
                        currentMissionId=current_mission_id,
                        position25832=pos_25832
                    ))
                except Exception as ent_err:
                    logger.warning(f"Failed to parse Robot entity: {ent_err}")
                    continue
            # Normalize and deduplicate robots where IDs have an extra 'Robot:' prefix
            def normalize_id(rid: str) -> str:
                if rid.startswith("Robot:"):
                    return rid.split("Robot:", 1)[1]
                return rid
            def normalize_name(name_val: Optional[str]) -> Optional[str]:
                if isinstance(name_val, str) and name_val.startswith("Robot:"):
                    return name_val.split("Robot:", 1)[1]
                return name_val

            aggregated: dict[str, RobotInfo] = {}
            for r in robots_parsed:
                norm_id = normalize_id(r.robotId)
                r.robotId = norm_id
                r.name = normalize_name(r.name) or norm_id
                existing = aggregated.get(norm_id)
                if existing is None:
                    aggregated[norm_id] = r
                    continue
                # Prefer entry with position, then newer lastSeen, then with battery/state
                def has_pos(x: RobotInfo) -> bool:
                    return x.position25832 is not None
                def last_seen_ts(x: RobotInfo) -> str:
                    return x.lastSeen or ""
                choose = existing
                if has_pos(r) and not has_pos(existing):
                    choose = r
                elif has_pos(r) == has_pos(existing):
                    if last_seen_ts(r) > last_seen_ts(existing):
                        choose = r
                    elif last_seen_ts(r) == last_seen_ts(existing):
                        # Prefer with battery or state populated
                        if (r.batteryPct is not None and existing.batteryPct is None) or (r.state and not existing.state):
                            choose = r
                aggregated[norm_id] = choose
            return list(aggregated.values())
    except (httpx.ConnectError, httpx.TimeoutException, ConnectionError, OSError) as e:
        logger.error(f"FIWARE Orion Context Broker not accessible: {str(e)}")
        raise HTTPException(status_code=503, detail="FIWARE Orion Context Broker not accessible. Please ensure FIWARE infrastructure is running.")
    except httpx.HTTPError as e:
        logger.error(f"Error listing robots from Orion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing robots from FIWARE: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error listing robots from Orion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error listing robots from FIWARE: {str(e)}")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.append(websocket)
    logger.info("WebSocket client connected")
    try:
        while True:
            # Keepalive: receive pings from client if any; we won't process incoming messages for now
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    finally:
        if websocket in connected_websockets:
            connected_websockets.remove(websocket)

async def ws_broadcast_loop():
    while True:
        try:
            if connected_websockets:
                robots = await list_robots_from_orion()
                payload = {
                    "type": "robot_snapshot",
                    "ts": datetime.utcnow().isoformat() + "Z",
                    "robots": [r.model_dump() for r in robots],
                }
                living_clients: List[WebSocket] = []
                for ws in connected_websockets:
                    try:
                        await ws.send_text(json.dumps(payload))
                        living_clients.append(ws)
                    except Exception as e:
                        logger.warning(f"Dropping WS client due to send error: {e}")
                connected_websockets[:] = living_clients
        except Exception as e:
            logger.error(f"WS broadcast loop error: {e}")
        # Broadcast interval
        await asyncio.sleep(2.0)

def convert_to_utc_format(timestamp_str):
    """
    Convert timestamp string to UTC format for FIWARE compatibility.
    Input can be in various formats like '2025-07-26T21:44:30.669265+02:00'
    Output will be in format '2025-07-26T19:44:30.669Z'
    """
    try:
        # Parse the timestamp with timezone awareness
        dt = date_parser.isoparse(timestamp_str)
        
        # Convert to UTC
        dt_utc = dt.astimezone(pytz.UTC)
        
        # Format for FIWARE (ISO8601 with Z suffix, remove microseconds if > 3 digits)
        utc_str = dt_utc.strftime('%Y-%m-%dT%H:%M:%S')
        
        # Add milliseconds if present (max 3 digits)
        if dt_utc.microsecond:
            milliseconds = dt_utc.microsecond // 1000
            utc_str += f".{milliseconds:03d}"
        
        utc_str += "Z"
        
        logger.debug(f"🕐 Timestamp conversion: {timestamp_str} → {utc_str}")
        return utc_str
        
    except Exception as e:
        logger.warning(f"Failed to convert timestamp '{timestamp_str}': {e}")
        # Fallback: if it's already in a good format, return as-is
        if timestamp_str.endswith('Z'):
            return timestamp_str
        # Otherwise, try to append Z
        return timestamp_str.replace('+00:00', 'Z')

def validate_utm_coordinates(x, y, max_coord=1000000.0, min_coord=-1000000.0):
    """
    Validate UTM coordinates are within reasonable ranges
    
    Args:
        x (float): X coordinate
        y (float): Y coordinate
        max_coord (float): Maximum allowed coordinate value
        min_coord (float): Minimum allowed coordinate value
    
    Raises:
        HTTPException: If coordinates are out of range
    """
    if not (min_coord <= x <= max_coord and min_coord <= y <= max_coord):
        raise HTTPException(
            status_code=400,
            detail=f"UTM coordinates out of range. X and Y must be between {min_coord} and {max_coord}. Received: [{x}, {y}]"
        )


# FIWARE Orion Integration Functions
async def create_mission_entity(mission: Mission):
    """Create mission entity in FIWARE Orion Context Broker (stores WGS84 in command)"""

    # Ensure waypoints inside command are converted to WGS84 before storage
    # Convert CommandMessage to dict for JSON serialization
    if hasattr(mission.command, 'model_dump'):
        command_data = mission.command.model_dump()
    elif hasattr(mission.command, 'dict'):
        command_data = mission.command.dict()
    else:
        command_data = dict(mission.command)

    try:
        if isinstance(command_data, dict):
            wp = command_data.get("waypoints", {})
            if isinstance(wp, dict) and wp.get("type") == "Point":
                coords = wp.get("coordinates", [])
                if len(coords) >= 2:
                    x_utm, y_utm = coords[:2]
                    lon, lat = transform_epsg_to_wgs84(x_utm, y_utm)
                    # Preserve any altitude component
                    new_coords = [lon, lat] + coords[2:]
                    command_data["waypoints"]["coordinates"] = new_coords
                    logger.info(
                        f"🔄 Waypoints converted to WGS84 for FIWARE: UTM[{x_utm}, {y_utm}] → WGS84[{lon:.6f}, {lat:.6f}]"
                    )
    except Exception as e:
        logger.error(f"❌ Failed to convert waypoints to WGS84: {str(e)}")
        # Continue with original command_data

    entity = {
        "id": f"urn:ngsi-ld:Mission:{mission.command.missionId}",
        "type": "Mission",
        "robotId": {
            "type": "Relationship",
            "value": f"urn:ngsi-ld:Robot:{mission.robotId}"
        },
        "sentTime": {
            "type": "DateTime",
            "value": mission.sentTime
        },
        "status": {
            "type": "Property",
            "value": mission.status
        },
        "command": {
            "type": "Property",
            "value": command_data
        },
        "completedTime": {
            "type": "DateTime",
            "value": mission.completedTime
        },
        "executedTime": {
            "type": "DateTime",
            "value": mission.executedTime
        },
        "fiwareResponse": {
            "type": "Property",
            "value": mission.fiwareResponse or {}
        },
        "developmentMode": {
            "type": "Property",
            "value": mission.developmentMode
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "fiware-service": FIWARE_SERVICE,
        "fiware-servicepath": FIWARE_SERVICE_PATH
    }
    
    # Log the entity being sent for debugging
    logger.info(f"🔍 Creating Orion entity: {mission.command.missionId}")
    logger.info(f"   Entity payload: {json.dumps(entity, indent=2)}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                FIWARE_ORION_URL,
                json=entity,
                headers=headers,
                timeout=10.0
            )
            response.raise_for_status()
            logger.info(f"Mission entity created in Orion: {mission.command.missionId}")
            
            # Handle Orion response (may be empty for 201 Created)
            try:
                if response.text.strip():
                    return response.json()
                else:
                    # Empty response is normal for 201 Created
                    logger.info("Orion returned empty response for entity creation (success)")
                    return {
                        "status": "created", 
                        "message": "Mission entity created in Orion Context Broker",
                        "status_code": response.status_code
                    }
            except ValueError as json_error:
                # Non-JSON response, log it and return status info
                logger.warning(f"Orion returned non-JSON response: {response.text}")
                return {
                    "status": "created",
                    "message": "Mission entity created in Orion Context Broker", 
                    "raw_response": response.text,
                    "status_code": response.status_code
                }
    except (httpx.ConnectError, httpx.TimeoutException, ConnectionError, OSError) as e:
        logger.error(f"FIWARE Orion Context Broker not accessible: {str(e)}")
        raise HTTPException(
            status_code=503, 
            detail="FIWARE Orion Context Broker not accessible. Please ensure FIWARE infrastructure is running."
        )
    except httpx.HTTPError as e:
        # Enhanced error logging to capture the actual error message from Orion
        error_detail = f"Error creating mission entity in Orion: {str(e)}"
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"❌ Orion HTTP Error:")
            logger.error(f"   Status code: {e.response.status_code}")
            logger.error(f"   Response body: {e.response.text}")
            logger.error(f"   Response headers: {dict(e.response.headers)}")
            error_detail = f"Orion returned {e.response.status_code}: {e.response.text}"
        else:
            logger.error(f"❌ HTTP Error (no response): {str(e)}")
        
        raise HTTPException(status_code=500, detail=f"Error storing mission in FIWARE: {error_detail}")
    except Exception as e:
        logger.error(f"Unexpected error creating mission entity in Orion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error storing mission in FIWARE: {str(e)}")

async def get_mission_from_orion(mission_id: str):
    """Retrieve mission entity from FIWARE Orion Context Broker"""
    entity_id = f"urn:ngsi-ld:Mission:{mission_id}"
    
    headers = {
        "Accept": "application/json",
        "fiware-service": FIWARE_SERVICE,
        "fiware-servicepath": FIWARE_SERVICE_PATH
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{FIWARE_ORION_URL}/{entity_id}",
                headers=headers,
                timeout=10.0
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            
            entity = response.json()
            logger.info(f"🔍 Retrieved mission entity from Orion: {mission_id}")
            
            # Safe field extraction with defaults
            def safe_get_value(entity, field_name, default=None):
                """Safely extract value from NGSI entity field"""
                field = entity.get(field_name, {})
                if isinstance(field, dict):
                    return field.get("value", default)
                return default
            
            def safe_get_relationship_value(entity, field_name, prefix="", default=""):
                """Safely extract relationship value and remove prefix"""
                value = safe_get_value(entity, field_name, default)
                if prefix and value.startswith(prefix):
                    return value.replace(prefix, "")
                return value
            
            # Extract fields safely
            robot_id = safe_get_relationship_value(entity, "robotId", "urn:ngsi-ld:Robot:", "unknown")
            command = safe_get_value(entity, "command", {})
            status = safe_get_value(entity, "status", "unknown")
            sent_time = safe_get_value(entity, "sentTime", "")
            executed_time = safe_get_value(entity, "executedTime", "")
            completed_time = safe_get_value(entity, "completedTime", "")
            fiware_response = safe_get_value(entity, "fiwareResponse", {})
            development_mode = safe_get_value(entity, "developmentMode", False)
            
            # Convert NGSI entity back to Mission model
            mission = Mission(
                robotId=robot_id,
                status=status,
                command=command,
                sentTime=sent_time,
                executedTime=executed_time,
                completedTime=completed_time,
                fiwareResponse=fiware_response,
                developmentMode=development_mode
            )
            return mission
    except (httpx.ConnectError, httpx.TimeoutException, ConnectionError, OSError) as e:
        logger.error(f"FIWARE Orion Context Broker not accessible: {str(e)}")
        raise HTTPException(
            status_code=503, 
            detail="FIWARE Orion Context Broker not accessible. Please ensure FIWARE infrastructure is running."
        )
    except httpx.HTTPError as e:
        logger.error(f"Error retrieving mission from Orion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving mission from FIWARE: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error retrieving mission from Orion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error retrieving mission from FIWARE: {str(e)}")

async def list_missions_from_orion():
    """List all mission entities from FIWARE Orion Context Broker"""
    params = {
        "type": "Mission",
        "limit": "1000"
    }
    
    headers = {
        "Accept": "application/json",
        "fiware-service": FIWARE_SERVICE,
        "fiware-servicepath": FIWARE_SERVICE_PATH
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                FIWARE_ORION_URL,
                params=params,
                headers=headers,
                timeout=10.0
            )
            response.raise_for_status()
            
            entities = response.json()
            logger.info(f"🔍 Retrieved {len(entities)} entities from Orion")
            missions = []
            
            for i, entity in enumerate(entities):
                try:
                    logger.info(f"   Processing entity {i+1}: {entity.get('id', 'unknown')}")
                    
                    # Extract mission ID safely
                    mission_id = entity.get("id", "").replace("urn:ngsi-ld:Mission:", "")
                    if not mission_id:
                        logger.warning(f"   Skipping entity with missing or invalid ID: {entity.get('id')}")
                        continue
                    
                    # Safe field extraction with defaults
                    def safe_get_value(entity, field_name, default=None):
                        """Safely extract value from NGSI entity field"""
                        field = entity.get(field_name, {})
                        if isinstance(field, dict):
                            return field.get("value", default)
                        return default
                    
                    def safe_get_relationship_value(entity, field_name, prefix="", default=""):
                        """Safely extract relationship value and remove prefix"""
                        value = safe_get_value(entity, field_name, default)
                        if prefix and value.startswith(prefix):
                            return value.replace(prefix, "")
                        return value
                    
                    # Extract fields safely
                    robot_id = safe_get_relationship_value(entity, "robotId", "urn:ngsi-ld:Robot:", "unknown")
                    command = safe_get_value(entity, "command", {})
                    status = safe_get_value(entity, "status", "unknown")
                    sent_time = safe_get_value(entity, "sentTime", "")
                    executed_time = safe_get_value(entity, "executedTime", "")
                    completed_time = safe_get_value(entity, "completedTime", "")
                    fiware_response = safe_get_value(entity, "fiwareResponse", {})
                    development_mode = safe_get_value(entity, "developmentMode", False)
                    
                    logger.info(f"   Extracted: robotId={robot_id}, status={status}")
                    
                    mission = Mission(
                        robotId=robot_id,
                        status=status,
                        command=command,
                        sentTime=sent_time,
                        executedTime=executed_time,
                        completedTime=completed_time,
                        fiwareResponse=fiware_response,
                        developmentMode=development_mode
                    )
                    missions.append(mission)
                    
                except Exception as entity_error:
                    logger.error(f"   Error processing entity {i+1}: {str(entity_error)}")
                    logger.error(f"   Entity content: {json.dumps(entity, indent=2)}")
                    # Continue processing other entities instead of failing completely
                    continue
            
            logger.info(f"✅ Successfully processed {len(missions)} missions from Orion")
            return missions
            
    except (httpx.ConnectError, httpx.TimeoutException, ConnectionError, OSError) as e:
        logger.error(f"FIWARE Orion Context Broker not accessible: {str(e)}")
        raise HTTPException(
            status_code=503, 
            detail="FIWARE Orion Context Broker not accessible. Please ensure FIWARE infrastructure is running."
        )
    except httpx.HTTPError as e:
        logger.error(f"Error listing missions from Orion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing missions from FIWARE: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error listing missions from Orion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error listing missions from FIWARE: {str(e)}")

# FIWARE Orion Integration Functions for ScheduledMission
async def create_scheduled_mission_entity(scheduled_mission: ScheduledMission):
    """Create scheduled mission entity in FIWARE Orion Context Broker."""
    entity = {
        "id": f"urn:ngsi-ld:ScheduledMission:{scheduled_mission.command.missionId}",
        "type": "ScheduledMission",
        "robotId": {
            "type": "Relationship",
            "value": f"urn:ngsi-ld:Robot:{scheduled_mission.robotId}"
        },
        "scheduleType": {
            "type": "Property",
            "value": scheduled_mission.scheduleType
        },
        "estimatedDuration": {
            "type": "Property",
            "value": scheduled_mission.estimatedDuration
        },
        "status": {
            "type": "Property",
            "value": scheduled_mission.status
        },
        "command": {
            "type": "Property",
            "value": scheduled_mission.command.model_dump() if hasattr(scheduled_mission.command, 'model_dump') else dict(scheduled_mission.command)
        },
        "sentTime": {
            "type": "DateTime",
            "value": scheduled_mission.sentTime
        },
        "completedTime": {
            "type": "DateTime",
            "value": scheduled_mission.completedTime
        },
        "executedTime": {
            "type": "DateTime",
            "value": scheduled_mission.executedTime
        },
        "maxRetries": {
            "type": "Property",
            "value": scheduled_mission.maxRetries
        },
        "retryCount": {
            "type": "Property",
            "value": scheduled_mission.retryCount
        }
    }
    
    # Add optional fields
    if scheduled_mission.scheduledTime:
        entity["scheduledTime"] = {
            "type": "DateTime",
            "value": scheduled_mission.scheduledTime
        }
    
    if scheduled_mission.cron:
        entity["cron"] = {
            "type": "Property",
            "value": scheduled_mission.cron
        }
    
    if scheduled_mission.errorMessage:
        entity["errorMessage"] = {"type": "Property", "value": scheduled_mission.errorMessage}
    
    if scheduled_mission.lastError:
        entity["lastError"] = {"type": "Property", "value": scheduled_mission.lastError}
    
    # Remove None fields, but keep timestamp fields even if they're None
    # This ensures the fields exist in Orion for later updates
    entity = {k: v for k, v in entity.items() if v is not None or k in ["sentTime", "executedTime", "completedTime"]}
    headers = {
        "Content-Type": "application/json",
        "fiware-service": FIWARE_SERVICE,
        "fiware-servicepath": FIWARE_SERVICE_PATH
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                FIWARE_ORION_URL,
                json=entity,
                headers=headers,
                timeout=10.0
            )
            response.raise_for_status()
            return response.json() if response.text.strip() else {"status": "created"}
    except Exception as e:
        logger.error(f"Error creating scheduled mission in Orion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating scheduled mission in Orion: {str(e)}")

async def get_scheduled_mission_from_orion(mission_id: str):
    entity_id = f"urn:ngsi-ld:ScheduledMission:{mission_id}"
    headers = {
        "Accept": "application/json",
        "fiware-service": FIWARE_SERVICE,
        "fiware-servicepath": FIWARE_SERVICE_PATH
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{FIWARE_ORION_URL}/{entity_id}",
                headers=headers,
                timeout=10.0
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            entity = response.json()
            # Parse entity to ScheduledMission
            def safe_get_value(entity, field_name, default=None):
                field = entity.get(field_name, {})
                if isinstance(field, dict):
                    return field.get("value", default)
                return default
            robot_id_full = safe_get_value(entity, "robotId", "unknown")
            # Extract robot ID from full URN if it's a relationship
            if robot_id_full.startswith("urn:ngsi-ld:Robot:"):
                robot_id = robot_id_full.replace("urn:ngsi-ld:Robot:", "")
            else:
                robot_id = robot_id_full
            scheduled_time = safe_get_value(entity, "scheduledTime", None)
            cron = safe_get_value(entity, "cron", None)
            schedule_type = safe_get_value(entity, "scheduleType", "once")
            estimated_duration = safe_get_value(entity, "estimatedDuration", None)
            status = safe_get_value(entity, "status", "unknown")
            command = safe_get_value(entity, "command", {})
            sent_time = safe_get_value(entity, "sentTime", None)
            executed_time = safe_get_value(entity, "executedTime", None)
            completed_time = safe_get_value(entity, "completedTime", None)
            error_message = safe_get_value(entity, "errorMessage", None)
            max_retries = safe_get_value(entity, "maxRetries", 3)
            retry_count = safe_get_value(entity, "retryCount", 0)
            last_error = safe_get_value(entity, "lastError", None)
            
            return ScheduledMission(
                robotId=robot_id,
                command=command,
                scheduledTime=scheduled_time,
                cron=cron,
                scheduleType=schedule_type,
                estimatedDuration=estimated_duration,
                status=status,
                sentTime=sent_time,
                executedTime=executed_time,
                completedTime=completed_time,
                errorMessage=error_message,
                maxRetries=max_retries,
                retryCount=retry_count,
                lastError=last_error
            )
    except Exception as e:
        logger.error(f"Error retrieving scheduled mission from Orion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving scheduled mission from Orion: {str(e)}")

async def list_scheduled_missions_from_orion():
    params = {"type": "ScheduledMission", "limit": "1000"}
    headers = {
        "Accept": "application/json",
        "fiware-service": FIWARE_SERVICE,
        "fiware-servicepath": FIWARE_SERVICE_PATH
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                FIWARE_ORION_URL,
                params=params,
                headers=headers,
                timeout=10.0
            )
            response.raise_for_status()
            entities = response.json()
            missions = []
            for entity in entities:
                mission_id = entity.get("id", "").replace("urn:ngsi-ld:ScheduledMission:", "")
                def safe_get_value(entity, field_name, default=None):
                    field = entity.get(field_name, {})
                    if isinstance(field, dict):
                        return field.get("value", default)
                    return default
                robot_id_full = safe_get_value(entity, "robotId", "unknown")
                # Extract robot ID from full URN if it's a relationship
                if robot_id_full.startswith("urn:ngsi-ld:Robot:"):
                    robot_id = robot_id_full.replace("urn:ngsi-ld:Robot:", "")
                else:
                    robot_id = robot_id_full
                scheduled_time = safe_get_value(entity, "scheduledTime", None)
                cron = safe_get_value(entity, "cron", None)
                schedule_type = safe_get_value(entity, "scheduleType", "once")
                estimated_duration = safe_get_value(entity, "estimatedDuration", None)
                status = safe_get_value(entity, "status", "unknown")
                command = safe_get_value(entity, "command", {})
                sent_time = safe_get_value(entity, "sentTime", None)
                executed_time = safe_get_value(entity, "executedTime", None)
                completed_time = safe_get_value(entity, "completedTime", None)
                error_message = safe_get_value(entity, "errorMessage", None)
                max_retries = safe_get_value(entity, "maxRetries", 3)
                retry_count = safe_get_value(entity, "retryCount", 0)
                last_error = safe_get_value(entity, "lastError", None)
                
                missions.append(ScheduledMission(
                    robotId=robot_id,
                    command=command,
                    scheduledTime=scheduled_time,
                    cron=cron,
                    scheduleType=schedule_type,
                    estimatedDuration=estimated_duration,
                    status=status,
                    sentTime=sent_time,
                    executedTime=executed_time,
                    completedTime=completed_time,
                    errorMessage=error_message,
                    maxRetries=max_retries,
                    retryCount=retry_count,
                    lastError=last_error
                ))
            return missions
    except Exception as e:
        logger.error(f"Error listing scheduled missions from Orion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing scheduled missions from Orion: {str(e)}")

async def update_scheduled_mission_status_in_orion(mission_id: str, status: str, **kwargs):
    """Update scheduled mission status in Orion Context Broker"""
    entity_id = f"urn:ngsi-ld:ScheduledMission:{mission_id}"
    
    # Validate status
    if status not in ["scheduled", "in_progress", "completed", "failed", "cancelled", "expired"]:
        raise HTTPException(status_code=400, detail="Invalid status. Allowed values: scheduled, in_progress, completed, failed, cancelled, expired")

    # Build complete update payload with all fields
    update_payload = {
        "status": {"type": "Property", "value": status}
    }
    
    # Add all additional fields to the payload
    for key, value in kwargs.items():
        if value is not None:
            # Use DateTime type for time-related fields and convert to UTC format for FIWARE compatibility
            if key in ["sentTime", "executedTime", "completedTime"]:
                # Convert to UTC format like regular missions do
                utc_value = convert_to_utc_format(value)
                update_payload[key] = {"type": "DateTime", "value": utc_value}
            else:
                update_payload[key] = {"type": "Property", "value": value}
    
    headers = {
        "Content-Type": "application/json",
        "fiware-service": FIWARE_SERVICE,
        "fiware-servicepath": FIWARE_SERVICE_PATH
    }
    
    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"Updating scheduled mission status in Orion: {entity_id}")
            logger.info(f"Complete payload: {update_payload}")
            
            # Use a single PATCH request with all fields
            response = await client.patch(
                f"{FIWARE_ORION_URL}/{entity_id}/attrs",
                json=update_payload,
                headers=headers,
                timeout=10.0
            )
            
            if response.status_code == 204:
                logger.info(f"Successfully updated scheduled mission status: {mission_id} -> {status}")
                return {"missionId": mission_id, "status": status, "message": "Scheduled mission status updated successfully"}
            else:
                logger.error(f"Failed to update scheduled mission status: {response.status_code} - {response.text}")
                # Try individual field updates as fallback
                logger.info("Attempting individual field updates as fallback...")
                return await _update_scheduled_mission_fields_individually(client, entity_id, status, kwargs, headers)
            
    except Exception as e:
        logger.error(f"Error updating scheduled mission status in Orion: {str(e)}")
        # Try individual field updates as fallback
        try:
            async with httpx.AsyncClient() as client:
                return await _update_scheduled_mission_fields_individually(client, entity_id, status, kwargs, headers)
        except Exception as fallback_error:
            logger.error(f"Fallback update also failed: {str(fallback_error)}")
            return {"missionId": mission_id, "status": status, "message": "Status update failed", "error": str(e)}

async def _update_scheduled_mission_fields_individually(client, entity_id: str, status: str, kwargs: dict, headers: dict):
    """Fallback method to update fields individually if bulk update fails"""
    try:
        # First update status
        status_payload = {"status": {"type": "Property", "value": status}}
        status_response = await client.patch(
            f"{FIWARE_ORION_URL}/{entity_id}/attrs",
            json=status_payload,
            headers=headers,
            timeout=10.0
        )
        
        if status_response.status_code != 204:
            logger.error(f"Status update failed: {status_response.status_code} - {status_response.text}")
            return {"missionId": entity_id.replace("urn:ngsi-ld:ScheduledMission:", ""), "status": status, "message": "Status update failed", "error": f"Status update failed: {status_response.status_code}"}
        
        # Then update additional fields individually
        updated_fields = []
        failed_fields = []
        
        for key, value in kwargs.items():
            if value is not None:
                try:
                    # Use DateTime type for time-related fields and convert to UTC format for FIWARE compatibility
                    if key in ["sentTime", "executedTime", "completedTime"]:
                        # Convert to UTC format like regular missions do
                        utc_value = convert_to_utc_format(value)
                        field_payload = {key: {"type": "DateTime", "value": utc_value}}
                    else:
                        field_payload = {key: {"type": "Property", "value": value}}
                    
                    field_response = await client.patch(
                        f"{FIWARE_ORION_URL}/{entity_id}/attrs",
                        json=field_payload,
                        headers=headers,
                        timeout=10.0
                    )
                    
                    if field_response.status_code == 204:
                        updated_fields.append(key)
                        logger.debug(f"Successfully updated field {key}")
                    else:
                        failed_fields.append(f"{key}: {field_response.status_code}")
                        logger.warning(f"Failed to update field {key}: {field_response.status_code} - {field_response.text}")
                        
                except Exception as field_error:
                    failed_fields.append(f"{key}: {str(field_error)}")
                    logger.warning(f"Error updating field {key}: {field_error}")
        
        mission_id = entity_id.replace("urn:ngsi-ld:ScheduledMission:", "")
        if failed_fields:
            logger.warning(f"Some fields failed to update: {failed_fields}")
            return {
                "missionId": mission_id, 
                "status": status, 
                "message": f"Status updated, but some fields failed: {failed_fields}",
                "updated_fields": updated_fields,
                "failed_fields": failed_fields
            }
        else:
            logger.info(f"All fields updated successfully for mission {mission_id}")
            return {"missionId": mission_id, "status": status, "message": "All fields updated successfully"}
            
    except Exception as e:
        logger.error(f"Individual field update failed: {str(e)}")
        return {"missionId": entity_id.replace("urn:ngsi-ld:ScheduledMission:", ""), "status": status, "message": "Individual field update failed", "error": str(e)}

async def delete_scheduled_mission_from_orion(mission_id: str):
    entity_id = f"urn:ngsi-ld:ScheduledMission:{mission_id}"
    headers = {
        "fiware-service": FIWARE_SERVICE,
        "fiware-servicepath": FIWARE_SERVICE_PATH
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{FIWARE_ORION_URL}/{entity_id}",
                headers=headers,
                timeout=10.0
            )
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Scheduled mission not found")
            response.raise_for_status()
            return {"missionId": mission_id, "message": "Scheduled mission deleted"}
    except Exception as e:
        logger.error(f"Error deleting scheduled mission from Orion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting scheduled mission from Orion: {str(e)}")


@app.get("/")
async def root():
    return {
        "message": "Mission Control Backend",
        "version": "1.0.0",
        "status": "operational"
    }

@app.get("/api/health")
async def health_check():
    # Count missions from FIWARE Orion
    try:
        missions = await list_missions_from_orion()
        missions_count = len(missions)
        orion_connected = True
    except HTTPException as e:
        if e.status_code == 503:
            missions_count = 0
            orion_connected = False
        else:
            missions_count = 0
            orion_connected = False
    except:
        missions_count = 0
        orion_connected = False
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "maps_count": len(os.listdir("maps")) if os.path.exists("maps") else 0,
        "active_missions": missions_count,
        "orion_connected": orion_connected,
        "fiware_required": True
    }

# Map Management Endpoints
@app.post("/api/maps/upload")
async def upload_map(
    map_yaml: UploadFile = File(..., description="Map YAML file (map.yaml)"),
    map_image: UploadFile = File(..., description="Map image file (map.png)")
):
    """Upload a new map with map.yaml and map.png files"""
    
    # Validate file names
    if not map_yaml.filename.endswith('.yaml'):
        raise HTTPException(status_code=400, detail="Map YAML file must have .yaml extension")
    if not map_image.filename.endswith(('.png', '.pgm')):
        raise HTTPException(status_code=400, detail="Map image file must have .png or .pgm extension")
    
    # Generate unique map ID
    map_id = f"map_{uuid.uuid4().hex[:8]}"
    
    # Get map-specific lock for upload operation
    with maps_lock:
        if map_id not in map_locks:
            map_locks[map_id] = Lock()
        map_lock = map_locks[map_id]
    
    # Use map-specific lock for this operation
    with map_lock:
        # Create map directory
        map_dir = f"maps/{map_id}"
        os.makedirs(map_dir, exist_ok=True)
    
    try:
        # Save YAML file as map.yaml
        yaml_path = f"{map_dir}/map.yaml"
        with open(yaml_path, "wb") as f:
            shutil.copyfileobj(map_yaml.file, f)
        
        # Save image file as map.png or map.pgm
        image_extension = map_image.filename.split('.')[-1]
        image_path = f"{map_dir}/map.{image_extension}"
        with open(image_path, "wb") as f:
            shutil.copyfileobj(map_image.file, f)
        
        # Parse YAML to extract map info
        with open(yaml_path, 'r') as f:
            map_config = yaml.safe_load(f)
        
        # Create map metadata for response
        map_info = MapInfo(
            mapId=map_id,
            name=map_yaml.filename.replace('.yaml', ''),
            resolution=map_config.get('resolution', 0.1),
            width=map_config.get('width', 0),
            height=map_config.get('height', 0),
            origin=map_config.get('origin', [0.0, 0.0, 0.0]),
            uploadTime=datetime.utcnow().isoformat()
        )
        
        logger.info(f"Map uploaded successfully: {map_id}")
        return {
            "mapId": map_id,
            "message": "Map uploaded successfully",
            "mapInfo": map_info
        }
        
    except Exception as e:
        # Cleanup on error
        if os.path.exists(map_dir):
            shutil.rmtree(map_dir)
        logger.error(f"Error uploading map: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error uploading map: {str(e)}")

@app.get("/api/robots")
async def list_robots():
    """List robots from FIWARE Orion as RobotInfo objects"""
    robots = await list_robots_from_orion()
    return {"robots": [r.model_dump() for r in robots], "count": len(robots)}

@app.get("/api/maps")
async def list_maps():
    """List all available maps by scanning the maps directory and reading map.yaml files"""
    # Use global maps lock for listing operation
    with maps_lock:
        maps_dir = "maps"
        maps = []
        if not os.path.exists(maps_dir):
            return {"maps": [], "count": 0}
        for map_id in os.listdir(maps_dir):
            map_dir = os.path.join(maps_dir, map_id)
            yaml_path = os.path.join(map_dir, "map.yaml")
            if os.path.isdir(map_dir) and os.path.exists(yaml_path):
                try:
                    with open(yaml_path, 'r') as f:
                        map_config = yaml.safe_load(f)
                    map_info = MapInfo(
                        mapId=map_id,
                        name=map_config.get('image', map_id).replace('.png', '').replace('.pgm', ''),
                        resolution=map_config.get('resolution', 0.1),
                        width=map_config.get('width', 0),
                        height=map_config.get('height', 0),
                        origin=map_config.get('origin', [0.0, 0.0, 0.0]),
                        uploadTime=datetime.utcfromtimestamp(os.path.getmtime(yaml_path)).isoformat()
                    )
                    maps.append(map_info)
                except Exception as e:
                    logger.warning(f"Failed to read map.yaml for {map_id}: {str(e)}")
                    continue
        return {"maps": maps, "count": len(maps)}

@app.get("/api/maps/{map_id}")
async def get_map_info(map_id: str):
    """Get information about a specific map by reading its map.yaml"""
    # Get map-specific lock for read operation
    with maps_lock:
        if map_id not in map_locks:
            map_locks[map_id] = Lock()
        map_lock = map_locks[map_id]
    
    # Use map-specific lock for this operation
    with map_lock:
        map_dir = f"maps/{map_id}"
        yaml_path = f"{map_dir}/map.yaml"
        if not os.path.exists(yaml_path):
            raise HTTPException(status_code=404, detail="Map not found")
        try:
            with open(yaml_path, 'r') as f:
                map_config = yaml.safe_load(f)
            map_info = MapInfo(
                mapId=map_id,
                name=map_config.get('image', map_id).replace('.png', '').replace('.pgm', ''),
                resolution=map_config.get('resolution', 0.1),
                width=map_config.get('width', 0),
                height=map_config.get('height', 0),
                origin=map_config.get('origin', [0.0, 0.0, 0.0]),
                uploadTime=datetime.utcfromtimestamp(os.path.getmtime(yaml_path)).isoformat()
            )
            return map_info
        except Exception as e:
            logger.error(f"Error reading map.yaml for {map_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error reading map.yaml: {str(e)}")

@app.get("/api/maps/{map_id}/files")
async def get_map_files_info(map_id: str):
    """Get map files information and download links for robots"""
    map_dir = f"maps/{map_id}"
    yaml_path = f"{map_dir}/map.yaml"
    if not os.path.exists(yaml_path):
        raise HTTPException(status_code=404, detail="Map not found")
    try:
        # Read YAML content
        with open(yaml_path, 'r') as f:
            yaml_content = f.read()
        # Find image file
        image_files = [f for f in os.listdir(map_dir) if f.startswith('map.') and f.endswith(('.png', '.pgm'))]
        if not image_files:
            raise HTTPException(status_code=404, detail="Map image file not found")
        return {
            "mapId": map_id,
            "files": {
                "yaml": {
                    "filename": "map.yaml",
                    "content": yaml_content,
                    "size": os.path.getsize(yaml_path)
                },
                "image": {
                    "filename": image_files[0],
                    "downloadUrl": f"/api/maps/{map_id}/image",
                    "size": os.path.getsize(f"{map_dir}/{image_files[0]}")
                }
            },
            "downloadLinks": {
                "yaml_file": f"/api/maps/{map_id}/yaml",
                "image_file": f"/api/maps/{map_id}/image"
            },
            "usage": {
                "robot": "Use yaml.content directly, download image via downloadUrl",
                "browser": "Use downloadLinks for file downloads"
            }
        }
    except Exception as e:
        logger.error(f"Error getting map files info: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting map files info: {str(e)}")

@app.get("/api/maps/{map_id}/yaml")
async def download_map_yaml(map_id: str):
    """Download map YAML file"""
    yaml_path = f"maps/{map_id}/map.yaml"
    if not os.path.exists(yaml_path):
        raise HTTPException(status_code=404, detail="Map not found")
    return FileResponse(yaml_path, filename="map.yaml")

@app.get("/api/maps/{map_id}/image")
async def download_map_image(map_id: str):
    """Serve map image file inline for browser rendering (PNG/PGM)."""
    map_dir = f"maps/{map_id}"
    if not os.path.exists(map_dir):
        raise HTTPException(status_code=404, detail="Map not found")
    image_files = [f for f in os.listdir(map_dir) if f.startswith('map.') and f.endswith(('.png', '.pgm'))]
    if not image_files:
        raise HTTPException(status_code=404, detail="Map image file not found")
    image_path = f"{map_dir}/{image_files[0]}"
    ext = os.path.splitext(image_path)[1].lower()
    media_type = "image/png" if ext == ".png" else "image/x-portable-graymap"
    # Serve inline so <img> / Leaflet can render it instead of forcing download
    return FileResponse(image_path, media_type=media_type, headers={"Content-Disposition": "inline"})

@app.delete("/api/maps/{map_id}")
async def delete_map(map_id: str):
    """Delete a map by map_id"""
    
    # Input validation - Task 6
    if not map_id.startswith("map_") or len(map_id) != 12 or not all(c in "abcdef0123456789" for c in map_id[4:]):
        raise HTTPException(status_code=400, detail="Invalid map_id format. Expected format: map_[a-f0-9]{8}")
    
    # Get map-specific lock - Task 7
    with maps_lock:
        if map_id not in map_locks:
            map_locks[map_id] = Lock()
        map_lock = map_locks[map_id]
    
    # Use map-specific lock for this operation
    with map_lock:
        try:
            # Map existence validation - Task 2
            map_dir = f"maps/{map_id}"
            yaml_path = f"{map_dir}/map.yaml"
            
            if not os.path.exists(yaml_path):
                raise HTTPException(status_code=404, detail="Map not found")
            
            # Read map info before deletion for response
            try:
                with open(yaml_path, 'r') as f:
                    map_config = yaml.safe_load(f)
                map_info = MapInfo(
                    mapId=map_id,
                    name=map_config.get('image', map_id).replace('.png', '').replace('.pgm', ''),
                    resolution=map_config.get('resolution', 0.1),
                    width=map_config.get('width', 0),
                    height=map_config.get('height', 0),
                    origin=map_config.get('origin', [0.0, 0.0, 0.0]),
                    uploadTime=datetime.utcfromtimestamp(os.path.getmtime(yaml_path)).isoformat()
                )
            except Exception as e:
                logger.warning(f"Failed to read map.yaml for {map_id} before deletion: {str(e)}")
                map_info = MapInfo(
                    mapId=map_id,
                    name=map_id,
                    resolution=0.1,
                    width=0,
                    height=0,
                    origin=[0.0, 0.0, 0.0],
                    uploadTime=datetime.utcnow().isoformat()
                )
            
            # Safe directory deletion - Task 3
            if os.path.exists(map_dir):
                shutil.rmtree(map_dir)
                logger.info(f"Map deleted successfully: {map_id}")
                
                # Clean up map-specific lock - Task 7
                with maps_lock:
                    if map_id in map_locks:
                        del map_locks[map_id]
                
                return {
                    "message": "Map deleted successfully",
                    "deletedMap": map_info
                }
            else:
                raise HTTPException(status_code=404, detail="Map directory not found")
                
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            # Comprehensive error handling - Task 4
            logger.error(f"Error deleting map {map_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error deleting map: {str(e)}")

# FIWARE Integration
async def send_fiware_command(robot_id: str, command_message: CommandMessage):
    """Send command to robot via FIWARE IoT Agent Direct API"""
    
    # Use IoT Agent direct command API as shown in professor's email
    # Correct payload format from professor's response
    # Handle both full URN and simple robot ID
    # Accept IDs in forms: 'urn:ngsi-ld:Robot:Professor_Robot_01', 'Robot:Professor_Robot_01', or 'Professor_Robot_01'
    if robot_id.startswith("urn:ngsi-ld:Robot:"):
        entity_id = robot_id
    elif robot_id.startswith("Robot:"):
        entity_id = f"urn:ngsi-ld:Robot:{robot_id.split('Robot:',1)[1]}"
    else:
        entity_id = f"urn:ngsi-ld:Robot:{robot_id}"
    
    # Transform waypoint coordinates from EPSG:25832 to WGS84 for robot
    waypoints_wgs84 = command_message.waypoints.model_dump()
    if waypoints_wgs84.get("type") == "Point" and "coordinates" in waypoints_wgs84:
        x_utm, y_utm = waypoints_wgs84["coordinates"][:2]
        logger.info(f"🔄 Transforming waypoint coordinates for robot:")
        logger.info(f"   Input UTM: [{x_utm}, {y_utm}]")
        
        try:
            # Transform to WGS84 for robot consumption
            lon, lat = transform_epsg_to_wgs84(x_utm, y_utm)
            waypoints_wgs84["coordinates"] = [lon, lat]
            if len(waypoints_wgs84["coordinates"]) > 2:
                waypoints_wgs84["coordinates"].append(0.0)  # Keep altitude if present
            
            logger.info(f"   Output WGS84: [{lon:.6f}, {lat:.6f}]")
            
        except HTTPException as e:
            logger.error(f"❌ Failed to transform waypoint coordinates: {str(e.detail)}")
            raise e
    
    # Create command payload as JSON string (as the professor suggested the value can be any string)
    command_payload = {
        "command": command_message.command,
        "commandTime": command_message.commandTime,
        "waypoints": waypoints_wgs84,  # Use transformed coordinates
        "mapId": command_message.mapId,
        "missionId": command_message.missionId
    }
    
    # Professor's correct payload structure
    fiware_payload = {
        "actionType": "update",
        "entities": [
            {
                "type": "Robot",
                "id": entity_id,
                "command": {
                    "type": "command",
                    "value": json.dumps(command_payload)
                }
            }
        ]
    }
    
    headers = {
        "Content-Type": "application/json",
        "fiware-service": FIWARE_SERVICE,
        "fiware-servicepath": FIWARE_SERVICE_PATH
    }
    
    # Log detailed information for debugging
    logger.info(f"🚀 Sending command to IoT Agent:")
    logger.info(f"   URL: {FIWARE_IOT_AGENT_URL}")
    logger.info(f"   Headers: {headers}")
    logger.info(f"   Payload: {fiware_payload}")
    
    try:
        async with httpx.AsyncClient() as client:
            # Use IoT Agent direct command API endpoint
            response = await client.post(
                FIWARE_IOT_AGENT_URL,
                json=fiware_payload,
                headers=headers,
                timeout=10.0
            )
            response.raise_for_status()
            logger.info(f"✅ IoT Agent response: Status {response.status_code}")
            logger.info(f"   Response body: {response.text}")
            logger.info(f"   Response headers: {dict(response.headers)}")
            logger.info(f"IoT Agent command sent successfully to {robot_id}")
            
            # Handle IoT Agent response (may be empty or non-JSON)
            try:
                if response.text.strip():
                    return response.json()
                else:
                    # Empty response is actually success for IoT Agent
                    logger.info("IoT Agent returned empty response (success)")
                    return {"status": "accepted", "message": "Command sent to IoT Agent"}
            except ValueError as json_error:
                # Non-JSON response, log it and return status info
                logger.warning(f"IoT Agent returned non-JSON response: {response.text}")
                return {
                    "status": "accepted", 
                    "message": "Command sent to IoT Agent",
                    "raw_response": response.text,
                    "status_code": response.status_code
                }
            
    except (httpx.ConnectError, httpx.TimeoutException, ConnectionError, OSError) as e:
        logger.error(f"FIWARE IoT Agent not accessible: {str(e)}")
        raise HTTPException(
            status_code=503, 
            detail="FIWARE IoT Agent not accessible. Please ensure FIWARE infrastructure is running."
        )
    except httpx.HTTPError as e:
        logger.error(f"❌ HTTP Error sending IoT Agent command: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"   Status code: {e.response.status_code}")
            logger.error(f"   Response body: {e.response.text}")
        raise HTTPException(status_code=500, detail=f"Error sending command to IoT Agent: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error sending IoT Agent command: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error sending command to IoT Agent: {str(e)}")

# Local MQTT Integration
async def send_local_mqtt_command(robot_id: str, command_message: CommandMessage):
    """Send command to robot via local MQTT broker"""
    
    # Define local MQTT topic structure
    command_topic = f"robot/{robot_id}/command"
    
    # Transform waypoint coordinates from EPSG:25832 to WGS84 for robot
    waypoints_wgs84 = command_message.waypoints.model_dump()
    if waypoints_wgs84.get("type") == "Point" and "coordinates" in waypoints_wgs84:
        x_utm, y_utm = waypoints_wgs84["coordinates"][:2]
        logger.info(f"🔄 Transforming waypoint coordinates for local MQTT:")
        logger.info(f"   Input UTM: [{x_utm}, {y_utm}]")
        
        try:
            # Transform to WGS84 for robot consumption
            lon, lat = transform_epsg_to_wgs84(x_utm, y_utm)
            waypoints_wgs84["coordinates"] = [lon, lat]
            if len(waypoints_wgs84["coordinates"]) > 2:
                waypoints_wgs84["coordinates"].append(0.0)  # Keep altitude if present
            
            logger.info(f"   Output WGS84: [{lon:.6f}, {lat:.6f}]")
            
        except HTTPException as e:
            logger.error(f"❌ Failed to transform waypoint coordinates: {str(e.detail)}")
            raise e
    
    # Create command payload matching robot expectations (nested structure)
    mqtt_payload = {
        "command": {
            "command": command_message.command,
            "commandTime": command_message.commandTime,
            "waypoints": waypoints_wgs84,  # Use transformed coordinates
            "mapId": command_message.mapId,
            "missionId": command_message.missionId
        }
    }
    
    # Log detailed information for debugging
    logger.info(f"🚀 Sending command to Local MQTT:")
    logger.info(f"   Broker: {LOCAL_MQTT_HOST}:{LOCAL_MQTT_PORT}")
    logger.info(f"   Topic: {command_topic}")
    logger.info(f"   Payload: {mqtt_payload}")
    
    try:
        # Create MQTT client
        client = mqtt.Client()
        
        # Set username/password if provided
        if LOCAL_MQTT_USERNAME and LOCAL_MQTT_PASSWORD:
            client.username_pw_set(LOCAL_MQTT_USERNAME, LOCAL_MQTT_PASSWORD)
        
        # Connect to broker
        client.connect(LOCAL_MQTT_HOST, LOCAL_MQTT_PORT, 60)
        
        # Publish command
        result = client.publish(command_topic, json.dumps(mqtt_payload))
        
        # Wait for message to be sent
        result.wait_for_publish()
        
        # Disconnect
        client.disconnect()
        
        logger.info(f"✅ Local MQTT command sent successfully to {robot_id}")
        logger.info(f"   Topic: {command_topic}")
        logger.info(f"   Message ID: {result.mid}")
        
        return {
            "status": "sent",
            "message": "Command sent to local MQTT broker",
            "topic": command_topic,
            "messageId": result.mid,
            "broker": f"{LOCAL_MQTT_HOST}:{LOCAL_MQTT_PORT}"
        }
        
    except Exception as e:
        logger.error(f"❌ Error sending local MQTT command: {str(e)}")
        raise HTTPException(
            status_code=503, 
            detail=f"Local MQTT broker not accessible: {str(e)}"
        )

def store_local_mission(mission: Mission):
    """Store mission in local storage for local MQTT mode"""
    with local_missions_lock:
        local_missions[mission.missionId] = mission
        logger.info(f"Mission stored locally: {mission.missionId}")

def get_local_mission(mission_id: str):
    """Get mission from local storage"""
    with local_missions_lock:
        return local_missions.get(mission_id)

def list_local_missions():
    """List all missions from local storage"""
    with local_missions_lock:
        return list(local_missions.values())

def update_local_mission_status(mission_id: str, status: str, **kwargs):
    """Update mission status in local storage"""
    with local_missions_lock:
        if mission_id in local_missions:
            mission = local_missions[mission_id]
            mission.status = status
            # Update other fields if provided
            for key, value in kwargs.items():
                if hasattr(mission, key):
                    setattr(mission, key, value)
            logger.info(f"Local mission status updated: {mission_id} -> {status}")
            return True
        return False

def delete_local_mission(mission_id: str):
    """Delete mission from local storage"""
    with local_missions_lock:
        if mission_id in local_missions:
            del local_missions[mission_id]
            logger.info(f"Local mission deleted: {mission_id}")
            return True
        return False

# Mission Control Endpoints
@app.post("/api/missions/send")
async def send_mission(mission: MissionRequest):
    """Send mission command to robot via FIWARE"""
    # Validate map exists via file system
    yaml_path = f"maps/{mission.mapId}/map.yaml"
    if not os.path.exists(yaml_path):
        raise HTTPException(status_code=404, detail="Map not found")
    
    # Create command message
    command_message = CommandMessage(
        command="MOVE_TO",
        commandTime=datetime.utcnow().isoformat() + "Z",
        waypoints=mission.destination,
        mapId=mission.mapId
    )
    
    # Generate mission ID
    mission_id = f"mission_{uuid.uuid4().hex[:8]}"
    
    # Add mission ID to the command message for robot tracking
    command_message.missionId = mission_id
    
    # Send to FIWARE IoT Agent
    try:
        fiware_response = await send_fiware_command(mission.robotId, command_message)
        status = "sent"
        message = "Mission command sent to robot via FIWARE"
        logger.info(f"Mission sent successfully: {mission_id}")
    except HTTPException as e:
        # Re-raise HTTPExceptions (like 503 from FIWARE) without changing status code
        logger.error(f"Error sending mission: {str(e.detail)}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected error sending mission: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error sending mission: {str(e)}")
    
    # Create mission object
    mission_obj = Mission(
        robotId=mission.robotId,
        command=command_message,
        status=status,
        completedTime=None,
        executedTime=None,
        sentTime=datetime.utcnow().isoformat(),
        fiwareResponse=fiware_response,
        developmentMode=False
    )
    
    # Store mission in FIWARE Orion Context Broker
    orion_response = await create_mission_entity(mission_obj)
    
    return {
        "missionId": mission_id,
        "status": status,
        "message": message,
        "fiwareResponse": fiware_response,
        "orionResponse": orion_response,
        "storageType": "FIWARE Orion Context Broker"
    }

@app.get("/api/missions")
async def list_missions():
    """List all missions from FIWARE Orion Context Broker"""
    missions = await list_missions_from_orion()
    
    # Convert Mission objects to dict for response
    missions_dict = [mission.model_dump() for mission in missions]
    
    return {
        "missions": missions_dict,
        "count": len(missions),
        "storageType": "FIWARE Orion Context Broker"
    }

@app.get("/api/missions/{mission_id}")
async def get_mission(mission_id: str):
    """Get specific mission details from FIWARE Orion Context Broker"""
    mission = await get_mission_from_orion(mission_id)
    
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    
    mission_dict = mission.model_dump()
    mission_dict["storageType"] = "FIWARE Orion Context Broker"
    
    return mission_dict


@app.patch("/api/missions/{mission_id}/status")
async def unified_update_mission_status(mission_id: str, update: dict = Body(...)):
    """
    Unified status update endpoint for both regular and scheduled missions.
    Example payload:
    {
      "status": "completed",
      "sentTime": "2025-07-25T09:00:00+02:00",
      "executedTime": "2025-07-25T09:05:00+02:00",
      "completedTime": "2025-07-25T09:10:00+02:00",
      "errorMessage": "Optional error message"
    }
    Allowed values for status: scheduled, in_progress, completed, failed, cancelled
    """
    allowed_fields = {"status", "sentTime", "executedTime", "completedTime", "errorMessage"}
    update_payload = {k: v for k, v in update.items() if k in allowed_fields}
    if not update_payload:
        raise HTTPException(status_code=400, detail="No updatable fields provided")
    
    logger.info(f"Mission status update request for {mission_id}: {update_payload}")
    status = update_payload.pop("status", None)
    if status is None:
        raise HTTPException(status_code=400, detail="'status' field is required in the payload.")
    if status not in ["scheduled", "in_progress", "completed", "failed", "cancelled", "expired"]:
        raise HTTPException(status_code=400, detail="Invalid status. Allowed values: scheduled, in_progress, completed, failed, cancelled, expired")
    
    # Try scheduled mission first (since that's what we're using)
    try:
        scheduled_mission = await get_scheduled_mission_from_orion(mission_id)
        if scheduled_mission:
            result = await update_scheduled_mission_status_in_orion(mission_id, status, **update_payload)
            return {"missionId": mission_id, "type": "scheduled", "status": status, "message": "Status updated successfully"}
    except Exception as e:
        logger.warning(f"Failed to update scheduled mission {mission_id}: {e}")
    
    # Try regular mission as fallback
    try:
        mission = await get_mission_from_orion(mission_id)
        if mission:
            # Update regular mission - only pass fields that MissionStatusUpdate accepts
            mission_update_fields = {}
            allowed_fields = ["robotPosition", "completedTime", "executedTime", "sentTime", "errorMessage"]
            for field in allowed_fields:
                if field in update_payload:
                    mission_update_fields[field] = update_payload[field]
            
            result = await update_mission_status(mission_id, MissionStatusUpdate(status=status, **mission_update_fields))
            return {"missionId": mission_id, "type": "regular", "status": status, "message": "Status updated successfully"}
    except Exception as e:
        logger.warning(f"Failed to update regular mission {mission_id}: {e}")
    
    # If we get here, neither mission type was found
    raise HTTPException(status_code=404, detail="Mission not found (neither regular nor scheduled)")

@app.delete("/api/missions/{mission_id}")
async def delete_mission(mission_id: str):
    """Delete mission from FIWARE Orion Context Broker"""
    entity_id = f"urn:ngsi-ld:Mission:{mission_id}"
    
    headers = {
        "fiware-service": FIWARE_SERVICE,
        "fiware-servicepath": FIWARE_SERVICE_PATH
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{FIWARE_ORION_URL}/{entity_id}",
                headers=headers,
                timeout=10.0
            )
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Mission not found")
            response.raise_for_status()
            
            logger.info(f"Mission deleted from Orion: {mission_id}")
            
            return {
                "missionId": mission_id,
                "message": "Mission deleted successfully",
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except HTTPException as e:
        # Re-raise HTTPExceptions (like 404) without changing status code
        raise e
    except (httpx.ConnectError, httpx.TimeoutException, ConnectionError, OSError) as e:
        logger.error(f"FIWARE Orion Context Broker not accessible: {str(e)}")
        raise HTTPException(
            status_code=503, 
            detail="FIWARE Orion Context Broker not accessible. Please ensure FIWARE infrastructure is running."
        )
    except httpx.HTTPError as e:
        logger.error(f"Error deleting mission from Orion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting mission from FIWARE: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error deleting mission: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error deleting mission: {str(e)}")

# Local MQTT Endpoints (separate from FIWARE)
@app.post("/api/local-mqtt/missions/send")
async def send_mission_local_mqtt(mission: MissionRequest):
    """Send mission command to robot via Local MQTT"""
    # Validate map exists via file system
    yaml_path = f"maps/{mission.mapId}/map.yaml"
    if not os.path.exists(yaml_path):
        raise HTTPException(status_code=404, detail="Map not found")
    
    # Validate coordinates are reasonable (prevent very large numbers)
    coords = mission.destination.coordinates
    if len(coords) >= 2:
        x, y = coords[0], coords[1]
        # Check for reasonable coordinate ranges (adjust based on your map scales)
        MAX_COORD = 10000.0  # Maximum coordinate value (adjust as needed)
        MIN_COORD = -10000.0  # Minimum coordinate value (adjust as needed)
        
        if not (MIN_COORD <= x <= MAX_COORD and MIN_COORD <= y <= MAX_COORD):
            logger.warning(f"⚠️ Invalid coordinates received: [{x}, {y}]")
            raise HTTPException(
                status_code=400, 
                detail=f"Coordinates out of range. X and Y must be between {MIN_COORD} and {MAX_COORD}. Received: [{x}, {y}]"
            )
        
        logger.info(f"✅ Coordinates validated: [{x}, {y}]")
    
    # Create command message
    command_message = CommandMessage(
        command="MOVE_TO",
        commandTime=datetime.utcnow().isoformat() + "Z",
        waypoints=mission.destination,
        mapId=mission.mapId
    )
    
    # Generate mission ID
    mission_id = f"mission_{uuid.uuid4().hex[:8]}"
    
    # Add mission ID to the command message for robot tracking
    command_message.missionId = mission_id
    
    # Send to Local MQTT
    try:
        mqtt_response = await send_local_mqtt_command(mission.robotId, command_message)
        status = "sent"
        message = "Mission command sent to robot via Local MQTT"
        logger.info(f"Mission sent successfully via Local MQTT: {mission_id}")
        
        # Create mission object for local storage
        mission_obj = Mission(
            robotId=mission.robotId,
            command=command_message,
            status=status,
            completedTime=None,
            executedTime=None,
            sentTime=datetime.utcnow().isoformat(),
            fiwareResponse=mqtt_response,  # Store MQTT response in this field
            developmentMode=True  # Mark as development mode
        )
        
        # Store mission locally
        store_local_mission(mission_obj)
        
        return {
            "missionId": mission_id,
            "status": status,
            "message": message,
            "mqttResponse": mqtt_response,
            "storageType": "Local Storage",
            "mode": "local"
        }
        
    except HTTPException as e:
        logger.error(f"Error sending mission via Local MQTT: {str(e.detail)}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected error sending mission via Local MQTT: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error sending mission via Local MQTT: {str(e)}")

@app.get("/api/local-mqtt/missions")
async def list_missions_local_mqtt():
    """List all missions from Local Storage"""
    missions = list_local_missions()
    missions_dict = [mission.model_dump() for mission in missions]
    
    return {
        "missions": missions_dict,
        "count": len(missions),
        "storageType": "Local Storage",
        "mode": "local"
    }

@app.get("/api/local-mqtt/missions/{mission_id}")
async def get_mission_local_mqtt(mission_id: str):
    """Get specific mission details from Local Storage"""
    mission = get_local_mission(mission_id)
    
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    
    mission_dict = mission.model_dump()
    mission_dict["storageType"] = "Local Storage"
    mission_dict["mode"] = "local"
    
    return mission_dict

@app.patch("/api/local-mqtt/missions/{mission_id}/status")
async def update_mission_status_local_mqtt(mission_id: str, status_update: MissionStatusUpdate):
    """Update mission status in Local Storage"""
    try:
        # Update status in local storage
        success = update_local_mission_status(
            mission_id, 
            status_update.status,
            robotPosition=status_update.robotPosition.model_dump() if status_update.robotPosition else None,
            completedTime=status_update.completedTime,
            errorMessage=status_update.errorMessage
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Mission not found")
        
        return {
            "missionId": mission_id,
            "status": status_update.status,
            "message": "Mission status updated successfully",
            "timestamp": datetime.utcnow().isoformat(),
            "mode": "local"
        }
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error updating mission status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error updating mission status: {str(e)}")

@app.delete("/api/local-mqtt/missions/{mission_id}")
async def delete_mission_local_mqtt(mission_id: str):
    """Delete mission from Local Storage"""
    success = delete_local_mission(mission_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Mission not found")
    
    return {
        "missionId": mission_id,
        "message": "Mission deleted successfully",
        "timestamp": datetime.utcnow().isoformat(),
        "mode": "local"
    }

# Robot Control Endpoints
@app.post("/api/robot/{robot_id}/stop")
async def stop_robot(robot_id: str):
    """Stop specific robot - sends STOP command via FIWARE IoT Agent"""
    
    # Validate robot_id (basic validation)
    if not robot_id or len(robot_id.strip()) == 0:
        raise HTTPException(status_code=400, detail="Invalid robot_id")
    
    # Create STOP command message
    command_message = CommandMessage(
        command="STOP",
        commandTime=datetime.utcnow().isoformat() + "Z",
        waypoints=Point(type="Point", coordinates=[0.0, 0.0, 0.0]),  # Dummy waypoints for STOP
        mapId=""  # No map needed for STOP command
    )
    
    logger.info(f"🛑 Sending STOP command to robot via FIWARE IoT Agent: {robot_id}")
    
    try:
        # Send command via FIWARE IoT Agent
        response = await send_fiware_command(robot_id, command_message)
        
        logger.info(f"✅ STOP command sent successfully to {robot_id} via FIWARE IoT Agent")
        
        return {
            "robotId": robot_id,
            "command": "STOP",
            "status": "sent",
            "message": f"STOP command sent to robot {robot_id} via FIWARE IoT Agent",
            "timestamp": datetime.utcnow().isoformat(),
            "mode": "fiware",
            "response": response
        }
        
    except HTTPException as e:
        # Re-raise HTTPExceptions (like 503 from MQTT) without changing status code
        logger.error(f"❌ Error sending STOP command to {robot_id}: {str(e.detail)}")
        raise e
    except Exception as e:
        logger.error(f"❌ Unexpected error sending STOP command to {robot_id}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Unexpected error sending STOP command: {str(e)}"
        )

@app.post("/api/robot/local-mqtt/{robot_id}/stop")
async def stop_robot_local_mqtt(robot_id: str):
    """Stop specific robot - sends STOP command via Local MQTT"""
    
    # Validate robot_id (basic validation)
    if not robot_id or len(robot_id.strip()) == 0:
        raise HTTPException(status_code=400, detail="Invalid robot_id")
    
    # Create STOP command message
    command_message = CommandMessage(
        command="STOP",
        commandTime=datetime.utcnow().isoformat() + "Z",
        waypoints=Point(type="Point", coordinates=[0.0, 0.0, 0.0]),  # Dummy waypoints for STOP
        mapId=""  # No map needed for STOP command
    )
    
    logger.info(f"🛑 Sending STOP command to robot via Local MQTT: {robot_id}")
    
    try:
        # Send command via Local MQTT
        response = await send_local_mqtt_command(robot_id, command_message)
        
        logger.info(f"✅ STOP command sent successfully to {robot_id} via Local MQTT")
        
        return {
            "robotId": robot_id,
            "command": "STOP",
            "status": "sent",
            "message": f"STOP command sent to robot {robot_id} via Local MQTT",
            "timestamp": datetime.utcnow().isoformat(),
            "mode": "local",
            "response": response
        }
        
    except HTTPException as e:
        # Re-raise HTTPExceptions (like 503 from MQTT) without changing status code
        logger.error(f"❌ Error sending STOP command to {robot_id}: {str(e.detail)}")
        raise e
    except Exception as e:
        logger.error(f"❌ Unexpected error sending STOP command to {robot_id}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Unexpected error sending STOP command: {str(e)}"
        )

@app.get("/api/local-mqtt/health")
async def health_check_local_mqtt():
    """Health check for Local MQTT mode"""
    missions_count = len(list_local_missions())
    
    # Test local MQTT connection
    try:
        client = mqtt.Client()
        if LOCAL_MQTT_USERNAME and LOCAL_MQTT_PASSWORD:
            client.username_pw_set(LOCAL_MQTT_USERNAME, LOCAL_MQTT_PASSWORD)
        client.connect(LOCAL_MQTT_HOST, LOCAL_MQTT_PORT, 60)
        client.disconnect()
        local_mqtt_connected = True
    except:
        local_mqtt_connected = False
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "mqtt_mode": "local",
        "maps_count": len(os.listdir("maps")) if os.path.exists("maps") else 0,
        "active_missions": missions_count,
        "local_mqtt_connected": local_mqtt_connected,
        "local_mqtt_broker": f"{LOCAL_MQTT_HOST}:{LOCAL_MQTT_PORT}",
        "fiware_required": False
    }

# Testing endpoints
@app.post("/api/test/local-mqtt")
async def test_local_mqtt_connection():
    """Test Local MQTT broker connectivity"""
    test_topic = "test/connection"
    test_message = {
        "test": "connection",
        "timestamp": datetime.utcnow().isoformat(),
        "from": "mission_control_backend"
    }
    
    try:
        # Create MQTT client
        client = mqtt.Client()
        
        # Set username/password if provided
        if LOCAL_MQTT_USERNAME and LOCAL_MQTT_PASSWORD:
            client.username_pw_set(LOCAL_MQTT_USERNAME, LOCAL_MQTT_PASSWORD)
        
        # Connect to broker
        client.connect(LOCAL_MQTT_HOST, LOCAL_MQTT_PORT, 60)
        
        # Publish test message
        result = client.publish(test_topic, json.dumps(test_message))
        result.wait_for_publish()
        
        # Disconnect
        client.disconnect()
        
        return {
            "status": "success",
            "broker": f"{LOCAL_MQTT_HOST}:{LOCAL_MQTT_PORT}",
            "topic": test_topic,
            "messageId": result.mid,
            "message": "Local MQTT broker connection successful",
            "testPayload": test_message
        }
        
    except Exception as e:
        logger.error(f"Local MQTT connection test failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "broker": f"{LOCAL_MQTT_HOST}:{LOCAL_MQTT_PORT}",
            "message": "Local MQTT broker connection failed"
        }

@app.post("/api/test/orion")
async def test_orion_connection():
    """Test FIWARE Orion Context Broker connectivity"""
    headers = {
        "Accept": "application/json",
        "fiware-service": FIWARE_SERVICE,
        "fiware-servicepath": FIWARE_SERVICE_PATH
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Test basic connectivity
            response = await client.get(
                f"{FIWARE_ORION_URL}?type=Mission&limit=1",
                headers=headers,
                timeout=5.0
            )
            
            # Try to parse response
            try:
                orion_data = response.json() if response.text.strip() else []
            except:
                orion_data = "Non-JSON response"
            
            return {
                "status": "success",
                "orion_status_code": response.status_code,
                "orion_response": response.text[:500] + "..." if len(response.text) > 500 else response.text,
                "orion_data": orion_data,
                "orion_headers": dict(response.headers),
                "message": "FIWARE Orion Context Broker connection successful",
                "url": FIWARE_ORION_URL,
                "fiware_service": FIWARE_SERVICE,
                "fiware_servicepath": FIWARE_SERVICE_PATH
            }
            
    except Exception as e:
        logger.error(f"Orion connection test failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "message": "FIWARE Orion Context Broker connection failed",
            "url": FIWARE_ORION_URL,
            "fiware_service": FIWARE_SERVICE,
            "fiware_servicepath": FIWARE_SERVICE_PATH
        }

@app.post("/api/test/fiware")
async def test_fiware_connection():
    """Test FIWARE IoT Agent connectivity"""
    test_payload = {
        "type": "CommandMessage",
        "id": "urn:ngsi-ld:Robot:test",
        "command": {
            "type": "command",
            "value": {
                "command": "TEST",
                "commandTime": datetime.utcnow().isoformat() + "Z"
            }
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "fiware-service": FIWARE_SERVICE,
        "fiware-servicepath": FIWARE_SERVICE_PATH
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                FIWARE_IOT_AGENT_URL,
                json=test_payload,
                headers=headers,
                timeout=5.0
            )
            
            return {
                "status": "success",
                "fiware_status_code": response.status_code,
                "fiware_response": response.text,
                "message": "FIWARE IoT Agent connection successful"
            }
            
    except Exception as e:
        logger.error(f"FIWARE connection test failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "message": "FIWARE IoT Agent connection failed"
        }

@app.post("/api/test/coordinates")
async def test_coordinate_transformations():
    """Test coordinate transformation system"""
    
    # Test coordinates (example German UTM Zone 32N coordinates)
    test_coordinates = [
        {"name": "Dortmund Campus", "utm": [392846.925, 5707223.0]},
        {"name": "Center Point", "utm": [400000.0, 5700000.0]},
        {"name": "Edge Case", "utm": [500000.0, 5800000.0]}
    ]
    
    results = []
    
    try:
        for test_case in test_coordinates:
            x_utm, y_utm = test_case["utm"]
            
            # Test EPSG:25832 → WGS84 transformation
            try:
                lon, lat = transform_epsg_to_wgs84(x_utm, y_utm)
                
                # Test reverse transformation WGS84 → EPSG:25832
                x_back, y_back = transform_wgs84_to_epsg(lat, lon)
                
                # Calculate transformation accuracy
                x_error = abs(x_utm - x_back)
                y_error = abs(y_utm - y_back)
                
                results.append({
                    "name": test_case["name"],
                    "original_utm": [x_utm, y_utm],
                    "transformed_wgs84": [lon, lat],
                    "reverse_utm": [x_back, y_back],
                    "accuracy": {
                        "x_error_meters": round(x_error, 3),
                        "y_error_meters": round(y_error, 3),
                        "total_error_meters": round((x_error**2 + y_error**2)**0.5, 3)
                    },
                    "status": "success"
                })
                
            except Exception as e:
                results.append({
                    "name": test_case["name"],
                    "original_utm": [x_utm, y_utm],
                    "error": str(e),
                    "status": "failed"
                })
        
        # Overall system status
        successful_tests = len([r for r in results if r["status"] == "success"])
        total_tests = len(results)
        
        return {
            "status": "success" if successful_tests == total_tests else "partial",
            "coordinate_system": {
                "source": "EPSG:25832 (UTM Zone 32N)",
                "target": "EPSG:4326 (WGS84)",
                "library": "pyproj"
            },
            "test_results": results,
            "summary": {
                "successful_tests": successful_tests,
                "total_tests": total_tests,
                "success_rate": f"{(successful_tests/total_tests)*100:.1f}%"
            },
            "transformation_available": epsg_to_wgs84_transformer is not None
        }
        
    except Exception as e:
        logger.error(f"Coordinate transformation test failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "message": "Coordinate transformation system test failed",
            "transformation_available": epsg_to_wgs84_transformer is not None
        }

@app.post("/api/scheduled-missions")
async def create_scheduled_mission(request: MissionScheduledRequest = Body(...)):
    """
    Create a scheduled mission.
    Request body examples:
    
    One-time mission:
    {
      "robotId": "Professor_Robot_01",
      "destination": {"type": "Point", "coordinates": [7.0, 51.5, 0.0]},
      "mapId": "map_abc123",
      "scheduledTime": "2024-06-10T15:30:00+02:00"
    }
    
    Recurring mission:
    {
      "robotId": "Professor_Robot_01", 
      "destination": {"type": "Point", "coordinates": [7.0, 51.5, 0.0]},
      "mapId": "map_abc123",
      "cron": "0 9 * * *"
    }
    
    scheduledTime must be ISO8601 (e.g. 2025-07-25T09:00:00+02:00) - submitted in German time (CET/CEST)
    cron must be valid cron expression (e.g. "0 9 * * *" for daily at 9 AM)
    """
    import uuid
    from datetime import datetime
    
    # Validate scheduling input
    try:
        schedule_type, schedule_value = validate_scheduling_input(request.scheduledTime, request.cron)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Validation error: {e}")

    # Auto-generate missionId first
    mission_id = f"mission_{uuid.uuid4().hex[:8]}"
    
    # Build CommandMessage as in regular mission
    command = CommandMessage(
        command="MOVE_TO",
        commandTime=datetime.utcnow().isoformat() + "Z",
        waypoints=request.destination,
        mapId=request.mapId,
        missionId=mission_id
    )
    
    # Create scheduled mission based on type
    if schedule_type == "once":
        # One-time mission
        scheduled_time_utc = date_parser.isoparse(schedule_value).astimezone(pytz.UTC)
        
        # Check if scheduledTime is in the past or now
        now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
        if scheduled_time_utc <= now_utc:
            raise HTTPException(status_code=400, detail="Cannot schedule a mission in the past or for a time that is already in progress.")
        
        scheduled_mission = ScheduledMission(
            robotId=request.robotId,
            command=command,
            scheduledTime=schedule_value,
            scheduleType="once",
            estimatedDuration=300,  # Default 5 min, can be adjusted
            status="scheduled",
            sentTime=None,
            executedTime=None,
            completedTime=None,
            errorMessage=None
        )
    else:
        # Recurring mission
        scheduled_mission = ScheduledMission(
            robotId=request.robotId,
            command=command,
            cron=schedule_value,
            scheduleType="recurring",
            estimatedDuration=300,  # Default 5 min, can be adjusted
            status="scheduled",
            sentTime=None,
            executedTime=None,
            completedTime=None,
            errorMessage=None
        )
    
    # Conflict detection (for both one-time and recurring missions)
    conflict = await check_scheduled_mission_conflict(scheduled_mission)
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)
    
    # Store in Orion
    orion_response = await create_scheduled_mission_entity(scheduled_mission)
    
    # Schedule with APScheduler
    try:
        schedule_mission_with_apscheduler(scheduled_mission)
    except Exception as e:
        logger.error(f"Failed to schedule mission with APScheduler: {e}")
        # Still create the mission in Orion, but log the scheduling failure
        orion_response["scheduling_warning"] = f"Mission created but scheduling failed: {e}"
    
    # Optionally store in-memory for dev/testing
    with scheduled_missions_lock:
        scheduled_missions.append(scheduled_mission)
    
    return {
        "missionId": mission_id,
        "status": "created",
        "scheduleType": schedule_type,
        "scheduleValue": schedule_value,
        "orionResponse": orion_response
    }

@app.get("/api/scheduled-missions")
async def list_scheduled_missions():
    """List all scheduled missions from Orion"""
    missions = await list_scheduled_missions_from_orion()
    return {"scheduledMissions": [m.model_dump() for m in missions], "count": len(missions)}

@app.get("/api/scheduled-missions/{mission_id}")
async def get_scheduled_mission(mission_id: str):
    """Get a specific scheduled mission from Orion"""
    mission = await get_scheduled_mission_from_orion(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Scheduled mission not found")
    return mission.model_dump()

@app.patch("/api/scheduled-missions/{mission_id}")
async def update_scheduled_mission(mission_id: str, update: dict = Body(...)):
    """
    Update a scheduled mission in Orion.
    Example payload:
    {
      "status": "completed",
      "sentTime": "2025-07-25T09:00:00+02:00",
      "executedTime": "2025-07-25T09:05:00+02:00",
      "completedTime": "2025-07-25T09:10:00+02:00",
      "errorMessage": "Optional error message"
    }
    Allowed fields: status, sentTime, executedTime, completedTime, errorMessage
    """
    # Only allow status and timing updates for now
    allowed_fields = {"status", "sentTime", "executedTime", "completedTime", "errorMessage"}
    update_payload = {k: v for k, v in update.items() if k in allowed_fields}
    if not update_payload:
        raise HTTPException(status_code=400, detail="No updatable fields provided")
    # Pop status from payload and pass as positional argument
    status = update_payload.pop("status", None)
    if status is None:
        raise HTTPException(status_code=400, detail="'status' field is required in the payload.")
    result = await update_scheduled_mission_status_in_orion(mission_id, status, **update_payload)
    return result

@app.delete("/api/scheduled-missions/{mission_id}")
async def delete_scheduled_mission(mission_id: str):
    """Delete a scheduled mission from Orion and APScheduler"""
    # Remove from APScheduler first
    try:
        # Remove one-time mission job
        one_time_job_id = f"mission_{mission_id}"
        if scheduler.get_job(one_time_job_id):
            scheduler.remove_job(one_time_job_id)
            logger.info(f"Removed one-time mission job: {one_time_job_id}")
        
        # Remove recurring mission job
        recurring_job_id = f"recurring_{mission_id}"
        if scheduler.get_job(recurring_job_id):
            scheduler.remove_job(recurring_job_id)
            logger.info(f"Removed recurring mission job: {recurring_job_id}")
            
    except Exception as e:
        logger.warning(f"Failed to remove APScheduler job for mission {mission_id}: {e}")
    
    # Remove from Orion
    result = await delete_scheduled_mission_from_orion(mission_id)
    
    # Remove from in-memory store
    with scheduled_missions_lock:
        scheduled_missions[:] = [m for m in scheduled_missions if m.command.missionId != mission_id]
    
    return result

@app.post("/api/scheduled-missions/execute-due")
async def execute_due_missions():
    """
    Manually trigger execution of due scheduled missions.
    Useful for testing the deadline-based execution logic.
    """
    try:
        await check_and_execute_due_missions()
        return {"status": "success", "message": "Due missions check completed"}
    except Exception as e:
        logger.error(f"Error executing due missions: {e}")
        raise HTTPException(status_code=500, detail=f"Error executing due missions: {e}")

@app.post("/api/scheduled-missions/cleanup-orphaned-jobs")
async def cleanup_orphaned_jobs_endpoint():
    """
    Manually clean up APScheduler jobs for missions that no longer exist in Orion.
    Useful when missions are deleted but jobs remain in the scheduler.
    """
    try:
        await cleanup_orphaned_jobs()
        return {"status": "success", "message": "Orphaned jobs cleanup completed"}
    except Exception as e:
        logger.error(f"Error cleaning up orphaned jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Error cleaning up orphaned jobs: {e}")

@app.post("/api/scheduled-missions/cleanup-all-jobs")
async def cleanup_all_jobs_endpoint():
    """
    Remove ALL APScheduler jobs. Use with caution - this will remove all scheduled missions.
    Useful for clearing orphaned jobs when Orion is empty.
    """
    try:
        jobs = scheduler.get_jobs()
        removed_count = 0
        
        for job in jobs:
            scheduler.remove_job(job.id)
            removed_count += 1
            logger.info(f"Removed job: {job.id}")
        
        return {
            "message": f"Removed {removed_count} APScheduler jobs",
            "removed_count": removed_count
        }
    except Exception as e:
        logger.error(f"Error cleaning up all jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cleanup jobs: {e}")

@app.post("/api/scheduled-missions/validate-missions")
async def validate_missions_endpoint():
    """Manually trigger mission validation and mark expired ones"""
    try:
        await validate_missions_on_startup()
        return {
            "message": "Mission validation completed successfully"
        }
    except Exception as e:
        logger.error(f"Error validating missions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to validate missions: {e}")

@app.get("/api/scheduled-missions/jobs")
async def list_apscheduler_jobs():
    """List all active APScheduler jobs"""
    try:
        jobs = scheduler.get_jobs()
        job_list = []
        
        for job in jobs:
            job_info = {
                "id": job.id,
                "name": job.name,
                "func": job.func.__name__,
                "args": job.args,
                "trigger": str(job.trigger),
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None
            }
            job_list.append(job_info)
        
        return {
            "total_jobs": len(jobs),
            "jobs": job_list
        }
    except Exception as e:
        logger.error(f"Error listing APScheduler jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list jobs: {e}")

def execute_scheduled_mission(mission_id: str):
    """Execute a single scheduled mission using APScheduler (synchronous wrapper for async function)"""
    try:
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the async function
        result = loop.run_until_complete(_execute_scheduled_mission_async(mission_id))
        
        # Clean up
        loop.close()
        
        return result
        
    except Exception as e:
        logger.error(f"Mission {mission_id} execution failed: {e}")
        # Try to update status in a new event loop
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(update_scheduled_mission_status_in_orion(
                mission_id, "failed", errorMessage=str(e)
            ))
            loop.close()
        except Exception as update_error:
            logger.error(f"Failed to update mission {mission_id} status: {update_error}")
        raise

async def _execute_scheduled_mission_async(mission_id: str):
    """Execute a single scheduled mission asynchronously"""
    try:
        # Get mission from Orion
        mission = await get_scheduled_mission_from_orion(mission_id)
        if not mission:
            logger.error(f"Mission {mission_id} not found in Orion")
            return
        
        # Check deadline for one-time missions
        if mission.scheduleType == "once" and mission.scheduledTime:
            if is_mission_expired(mission):
                await mark_mission_expired(mission_id)
                return
        
        # Send to robot (non-blocking)
        await send_fiware_command(mission.robotId, mission.command)
        
        # Update sentTime to record when mission was sent
        from datetime import datetime
        import pytz
        sent_time = datetime.now(pytz.timezone("Europe/Berlin")).isoformat()
        
        # Try to update sentTime, but don't fail if it doesn't work
        try:
            await update_scheduled_mission_status_in_orion(
                mission_id, "scheduled", sentTime=sent_time
            )
        except Exception as update_error:
            logger.warning(f"Failed to update sentTime for mission {mission_id}: {update_error}")
            # Continue execution even if status update fails
        
        logger.info(f"Mission {mission_id} sent to robot successfully")
        
    except Exception as e:
        logger.error(f"Mission {mission_id} execution failed: {e}")
        # Try to update mission status to failed, but don't fail if it doesn't work
        try:
            await update_scheduled_mission_status_in_orion(
                mission_id, "failed", errorMessage=str(e)
            )
        except Exception as update_error:
            logger.warning(f"Failed to update mission {mission_id} status to failed: {update_error}")
        # Don't re-raise the exception to prevent APScheduler from retrying
        # The mission will be marked as failed in the database

def is_mission_expired(mission: ScheduledMission) -> bool:
    """Check if a one-time mission has expired (more than 600 seconds overdue)"""
    try:
        if not mission.scheduledTime:
            return False
        
        scheduled_time = date_parser.isoparse(mission.scheduledTime)
        if scheduled_time.tzinfo is None:
            berlin = pytz.timezone("Europe/Berlin")
            scheduled_time = berlin.localize(scheduled_time)
        
        now_berlin = datetime.now(pytz.timezone("Europe/Berlin"))
        time_diff_seconds = (now_berlin - scheduled_time).total_seconds()
        
        return time_diff_seconds > 600  # More than 600 seconds overdue
    except Exception as e:
        logger.error(f"Error checking mission expiration: {e}")
        return False

async def mark_mission_expired(mission_id: str):
    """Mark a mission as expired"""
    try:
        await update_scheduled_mission_status_in_orion(
            mission_id, "expired", 
            errorMessage="Mission expired - more than 600 seconds overdue"
        )
        logger.warning(f"Mission {mission_id} marked as expired")
    except Exception as e:
        logger.error(f"Failed to mark mission {mission_id} as expired: {e}")

def schedule_mission_with_apscheduler(mission: ScheduledMission):
    """Schedule mission using APScheduler based on type"""
    try:
        if mission.scheduleType == "once" and mission.scheduledTime:
            # One-time mission
            scheduled_time = date_parser.isoparse(mission.scheduledTime)
            if scheduled_time.tzinfo is None:
                berlin = pytz.timezone("Europe/Berlin")
                scheduled_time = berlin.localize(scheduled_time)
            
            # Add some buffer time to ensure job doesn't get missed
            current_time = datetime.now(pytz.timezone("Europe/Berlin"))
            if scheduled_time <= current_time:
                logger.warning(f"Mission {mission.command.missionId} scheduled time {scheduled_time} is in the past, scheduling for immediate execution")
                scheduled_time = current_time + timedelta(seconds=5)  # 5 seconds from now
            
            job = scheduler.add_job(
                execute_scheduled_mission,
                'date',
                run_date=scheduled_time,
                args=[mission.command.missionId],
                id=f"mission_{mission.command.missionId}",
                replace_existing=True,
                misfire_grace_time=600  # Allow 600 seconds grace time for missed jobs
            )
            logger.info(f"Scheduled one-time mission {mission.command.missionId} for {scheduled_time} (job ID: {job.id})")
            
        elif mission.scheduleType == "recurring" and mission.cron:
            # Recurring mission with cron
            try:
                cron_params = parse_cron_expression(mission.cron)
                job = scheduler.add_job(
                    execute_scheduled_mission,
                    'cron',
                    args=[mission.command.missionId],
                    id=f"recurring_{mission.command.missionId}",
                    replace_existing=True,
                    misfire_grace_time=30,  # Allow 30 seconds grace time for missed jobs
                    **cron_params
                )
                logger.info(f"Scheduled recurring mission {mission.command.missionId} with cron {mission.cron} (job ID: {job.id})")
            except Exception as cron_error:
                logger.error(f"Failed to schedule recurring mission {mission.command.missionId} with cron {mission.cron}: {cron_error}")
                raise
        else:
            logger.error(f"Invalid mission configuration for {mission.command.missionId}")
            
    except Exception as e:
        logger.error(f"Failed to schedule mission {mission.command.missionId}: {e}")
        raise

def parse_cron_expression(cron_expr: str) -> dict:
    """Parse cron expression into APScheduler parameters"""
    # Example: "0 9 * * *" -> daily at 9 AM
    # Example: "*/5 * * * *" -> every 5 minutes
    # Example: "*/1 * * * *" -> every minute
    
    parts = cron_expr.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expr}. Expected 5 parts, got {len(parts)}")
    
    minute, hour, day, month, day_of_week = parts
    
    # Validate each part
    if not minute or not hour or not day or not month or not day_of_week:
        raise ValueError(f"Invalid cron expression: {cron_expr}. All parts must be specified")
    
    return {
        'minute': minute,
        'hour': hour,
        'day': day,
        'month': month,
        'day_of_week': day_of_week
    }

# Legacy function for backward compatibility
async def check_and_execute_due_missions():
    """
    Check for due scheduled missions and execute them with deadline logic.
    Implements the 600-second cutoff: if mission is missed by more than 600 seconds, mark as expired.
    """
    try:
        # Get all scheduled missions from Orion
        scheduled_missions = await list_scheduled_missions_from_orion()
        
        # Get current time in German timezone
        berlin_tz = pytz.timezone("Europe/Berlin")
        now_berlin = datetime.now(berlin_tz)
        
        for mission in scheduled_missions:
            # Skip missions that are not in "scheduled" status
            if mission.status != "scheduled":
                continue
            
            try:
                # Parse scheduled time
                scheduled_time = date_parser.isoparse(mission.scheduledTime)
                if scheduled_time.tzinfo is None:
                    # Assume Berlin timezone if no timezone info
                    scheduled_time = berlin_tz.localize(scheduled_time)
                
                # Calculate time difference in seconds
                time_diff_seconds = (now_berlin - scheduled_time).total_seconds()
                
                if time_diff_seconds >= 0:  # Mission is due or overdue
                    if time_diff_seconds <= 600:  # Within 600 seconds (10 minutes) - execute
                        logger.info(f"Executing due mission {mission.command.missionId} (overdue by {time_diff_seconds:.1f}s)")
                        
                        # Send mission to robot
                        await send_fiware_command(mission.robotId, mission.command)
                        
                        logger.info(f"Mission {mission.command.missionId} sent to robot successfully")
                        
                    else:  # More than 600 seconds overdue - mark as expired
                        logger.warning(f"Mission {mission.command.missionId} expired (overdue by {time_diff_seconds:.1f}s > 600s)")
                        
                        # Update mission status to expired
                        await update_scheduled_mission_status_in_orion(
                            mission.command.missionId,
                            "expired",
                            errorMessage=f"Mission expired - scheduled for {scheduled_time.isoformat()}, current time {now_berlin.isoformat()}, overdue by {time_diff_seconds:.1f} seconds"
                        )
                        
            except Exception as e:
                logger.error(f"Error processing scheduled mission {mission.command.missionId}: {e}")
                
    except Exception as e:
        logger.error(f"Error in scheduled mission executor: {e}")

def background_scheduler():
    """
    Background thread that runs the scheduled mission executor every 30 seconds.
    """
    global scheduler_running
    while scheduler_running:
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run the executor
            loop.run_until_complete(check_and_execute_due_missions())
            
            # Close the loop
            loop.close()
            
        except Exception as e:
            logger.error(f"Error in background scheduler: {e}")
        
        # Sleep for 30 seconds before next check
        time.sleep(30)

def job_error_listener(event):
    """Handle job execution errors"""
    if event.exception:
        logger.error(f"Job {event.job_id} failed: {event.exception}")
        logger.error(f"Job details: {event.job_id}, scheduled_run_time: {event.scheduled_run_time}, retval: {event.retval}")
        mission_id = event.job_id.replace("mission_", "").replace("recurring_", "")
        
        # Use threading to avoid event loop conflicts
        import threading
        def handle_failure_async():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(handle_mission_failure(mission_id, str(event.exception)))
                loop.close()
            except Exception as e:
                logger.error(f"Failed to handle mission failure: {e}")
        
        # Run in a separate thread to avoid event loop conflicts
        failure_thread = threading.Thread(target=handle_failure_async, daemon=True)
        failure_thread.start()

def job_executed_listener(event):
    """Handle successful job execution"""
    logger.info(f"Job {event.job_id} executed successfully")
    logger.info(f"Job details: {event.job_id}, scheduled_run_time: {event.scheduled_run_time}, retval: {event.retval}")

async def handle_mission_failure(mission_id: str, error_message: str):
    """Handle mission failure and retry logic"""
    try:
        # Get current mission to check retry count
        mission = await get_scheduled_mission_from_orion(mission_id)
        if not mission:
            return
        
        current_retries = getattr(mission, 'retryCount', 0)
        max_retries = getattr(mission, 'maxRetries', 3)
        
        if current_retries < max_retries:
            # Increment retry count
            await update_scheduled_mission_status_in_orion(
                mission_id, 
                "scheduled",  # Reset to scheduled for retry
                retryCount=current_retries + 1,
                lastError=error_message
            )
            logger.info(f"Mission {mission_id} will be retried ({current_retries + 1}/{max_retries})")
        else:
            # Max retries reached, mark as failed
            await update_scheduled_mission_status_in_orion(
                mission_id, 
                "failed",
                lastError=f"Max retries ({max_retries}) reached. Last error: {error_message}"
            )
            logger.error(f"Mission {mission_id} failed after {max_retries} retries")
            
    except Exception as e:
        logger.error(f"Error handling mission failure for {mission_id}: {e}")

async def cleanup_orphaned_jobs():
    """Clean up APScheduler jobs for missions that no longer exist in Orion"""
    try:
        # Get all scheduled missions from Orion
        missions = await list_scheduled_missions_from_orion()
        mission_ids = {mission.command.missionId for mission in missions}
        
        # Get all APScheduler jobs
        jobs = scheduler.get_jobs()
        removed_count = 0
        
        for job in jobs:
            job_id = job.id
            # Extract mission ID from job ID
            if job_id.startswith("mission_"):
                mission_id = job_id.replace("mission_", "")
            elif job_id.startswith("recurring_"):
                mission_id = job_id.replace("recurring_", "")
            else:
                continue
            
            # If mission doesn't exist in Orion, remove the job
            if mission_id not in mission_ids:
                scheduler.remove_job(job_id)
                logger.info(f"Removed orphaned job: {job_id} (mission {mission_id} not found in Orion)")
                removed_count += 1
        
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} orphaned APScheduler jobs")
        else:
            logger.info("No orphaned APScheduler jobs found")
            
    except Exception as e:
        logger.error(f"Error cleaning up orphaned jobs: {e}")

async def validate_missions_on_startup():
    """Validate all scheduled missions on startup and mark expired ones"""
    try:
        # Get all scheduled missions from Orion
        missions = await list_scheduled_missions_from_orion()
        expired_count = 0
        
        for mission in missions:
            # Only check one-time missions that are still scheduled
            if (mission.scheduleType == "once" and 
                mission.status == "scheduled" and 
                mission.scheduledTime):
                
                if is_mission_expired(mission):
                    await mark_mission_expired(mission.command.missionId)
                    expired_count += 1
                    logger.warning(f"Marked expired mission on startup: {mission.command.missionId}")
        
        if expired_count > 0:
            logger.info(f"Marked {expired_count} expired missions during startup validation")
        else:
            logger.info("No expired missions found during startup validation")
            
    except Exception as e:
        logger.error(f"Error validating missions on startup: {e}")

def start_scheduler():
    """Start the APScheduler"""
    try:
        # Register event listeners
        scheduler.add_listener(job_error_listener, EVENT_JOB_ERROR)
        scheduler.add_listener(job_executed_listener, EVENT_JOB_EXECUTED)
        
        # Start the scheduler
        scheduler.start()
        logger.info("APScheduler started successfully")
        
        # Clean up orphaned jobs and validate missions (deferred to avoid event loop conflicts)
        import threading
        def deferred_startup_tasks():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # First validate and mark expired missions
                loop.run_until_complete(validate_missions_on_startup())
                
                # Then clean up orphaned jobs
                loop.run_until_complete(cleanup_orphaned_jobs())
                
                loop.close()
            except Exception as e:
                logger.warning(f"Failed to complete startup tasks: {e}")
        
        # Run startup tasks in a separate thread to avoid event loop conflicts
        startup_thread = threading.Thread(target=deferred_startup_tasks, daemon=True)
        startup_thread.start()
        
        # Legacy scheduler variables for backward compatibility
        global scheduler_running
        scheduler_running = True
        
    except Exception as e:
        logger.error(f"Failed to start APScheduler: {e}")
        raise

def stop_scheduler():
    """Stop the APScheduler"""
    try:
        scheduler.shutdown()
        logger.info("APScheduler stopped")
        
        # Legacy scheduler variables for backward compatibility
        global scheduler_running
        scheduler_running = False
        
    except Exception as e:
        logger.error(f"Error stopping APScheduler: {e}")

async def update_mission_status(mission_id: str, status_update: MissionStatusUpdate):
    """Update mission status in FIWARE Orion Context Broker (regular missions)."""
    entity_id = f"urn:ngsi-ld:Mission:{mission_id}"
    # Build update payload
    update_payload = {
        "status": {
            "type": "Property",
            "value": status_update.status,
            "metadata": {
                "timestamp": {
                    "type": "DateTime",
                    "value": datetime.utcnow().isoformat() + "Z"
                }
            }
        }
    }
    # Add optional fields if provided
    if status_update.robotPosition:
        update_payload["robotPosition"] = {
            "type": "geo:json",
            "value": status_update.robotPosition.model_dump()
        }
    if status_update.completedTime:
        completed_time_utc = convert_to_utc_format(status_update.completedTime)
        update_payload["completedTime"] = {
            "type": "DateTime",
            "value": completed_time_utc
        }
    if status_update.executedTime:
        executed_time_utc = convert_to_utc_format(status_update.executedTime)
        update_payload["executedTime"] = {
            "type": "DateTime",
            "value": executed_time_utc
        }
    if status_update.sentTime:
        sent_time_utc = convert_to_utc_format(status_update.sentTime)
        update_payload["sentTime"] = {
            "type": "DateTime",
            "value": sent_time_utc
        }
    if status_update.errorMessage:
        update_payload["errorMessage"] = {
            "type": "Property",
            "value": status_update.errorMessage
        }
    headers = {
        "Content-Type": "application/json",
        "fiware-service": FIWARE_SERVICE,
        "fiware-servicepath": FIWARE_SERVICE_PATH
    }
    try:
        async with httpx.AsyncClient() as client:
            # Try PATCH first, then PUT as fallback
            response = await client.patch(
                f"{FIWARE_ORION_URL}/{entity_id}/attrs",
                json=update_payload,
                headers=headers,
                timeout=10.0
            )
            
            # If PATCH fails with 422 or 400, try individual attribute updates
            if response.status_code in [400, 422]:
                logger.warning(f"PATCH failed with {response.status_code}: {response.text}")
                logger.info(f"Trying individual attribute updates for {mission_id}")
                
                # Update status attribute individually using PUT
                status_payload = {
                    "type": "Property",
                    "value": status_update.status,
                    "metadata": {
                        "timestamp": {
                            "type": "DateTime",
                            "value": datetime.utcnow().isoformat() + "Z"
                        }
                    }
                }
                
                response = await client.put(
                    f"{FIWARE_ORION_URL}/{entity_id}/attrs/status",
                    json=status_payload,
                    headers=headers,
                    timeout=10.0
                )
                
                # Update other fields if provided
                if status_update.completedTime:
                    # Convert to UTC format for FIWARE compatibility
                    completed_time_utc = convert_to_utc_format(status_update.completedTime)
                    completed_time_payload = {
                        "type": "DateTime",
                        "value": completed_time_utc
                    }
                    await client.put(
                        f"{FIWARE_ORION_URL}/{entity_id}/attrs/completedTime",
                        json=completed_time_payload,
                        headers=headers,
                        timeout=10.0
                    )
                
                if status_update.executedTime:
                    # Convert to UTC format for FIWARE compatibility
                    executed_time_utc = convert_to_utc_format(status_update.executedTime)
                    executed_time_payload = {
                        "type": "DateTime",
                        "value": executed_time_utc
                    }
                    await client.put(
                        f"{FIWARE_ORION_URL}/{entity_id}/attrs/executedTime",
                        json=executed_time_payload,
                        headers=headers,
                        timeout=10.0
                    )
                
                if status_update.sentTime:
                    # Convert to UTC format for FIWARE compatibility
                    sent_time_utc = convert_to_utc_format(status_update.sentTime)
                    sent_time_payload = {
                        "type": "DateTime",
                        "value": sent_time_utc
                    }
                    await client.put(
                        f"{FIWARE_ORION_URL}/{entity_id}/attrs/sentTime",
                        json=sent_time_payload,
                        headers=headers,
                        timeout=10.0
                    )
                
                if status_update.errorMessage:
                    error_payload = {
                        "type": "Property",
                        "value": status_update.errorMessage
                    }
                    await client.put(
                        f"{FIWARE_ORION_URL}/{entity_id}/attrs/errorMessage",
                        json=error_payload,
                        headers=headers,
                        timeout=10.0
                    )
            
            response.raise_for_status()
            logger.info(f"Mission status updated in Orion: {mission_id} -> {status_update.status}")
            return {
                "missionId": mission_id,
                "status": status_update.status,
                "message": "Mission status updated successfully",
                "timestamp": datetime.utcnow().isoformat()
            }
    except (httpx.ConnectError, httpx.TimeoutException, ConnectionError, OSError) as e:
        logger.error(f"FIWARE Orion Context Broker not accessible: {str(e)}")
        raise HTTPException(
            status_code=503, 
            detail="FIWARE Orion Context Broker not accessible. Please ensure FIWARE infrastructure is running."
        )
    except httpx.HTTPError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Mission not found")
        logger.error(f"Error updating mission status in Orion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating mission status in FIWARE: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error updating mission status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error updating mission status: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 