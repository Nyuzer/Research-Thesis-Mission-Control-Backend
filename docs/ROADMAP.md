# Development Roadmap: Mission Control Platform Enhancements

## Context

This is a robotics fleet management platform (research thesis) built with FastAPI + React/TypeScript + FIWARE/MQTT + Leaflet (EPSG:25832). The platform currently supports instant/scheduled missions, map upload/management, real-time robot monitoring via WebSocket, and has light/dark theming with responsive design.

This roadmap covers 5 major features organized into phases with clear dependencies and implementation steps.

---

## Phase 1: Authentication & Authorization + MQTT Security

**Why first:** Security is foundational — all other features (statistics, zones, advanced missions) need to know *who* is performing actions and *what role* they have.

### 1A. Backend Auth System

**Files to create/modify:**
- `mission_control_backend/app/auth/__init__.py`
- `mission_control_backend/app/auth/models.py` — User model (Pydantic + MongoDB schema)
- `mission_control_backend/app/auth/database.py` — MongoDB users collection
- `mission_control_backend/app/auth/password.py` — bcrypt hashing
- `mission_control_backend/app/auth/jwt_handler.py` — JWT token create/verify
- `mission_control_backend/app/auth/config.py` — Auth settings (secret key, token expiry)
- `mission_control_backend/app/auth/dependencies.py` — FastAPI deps (`get_current_user`, `require_role`)
- `mission_control_backend/app/auth/router.py` — Auth routes (login, register, me, users CRUD)
- `mission_control_backend/app/auth/bootstrap.py` — Create default admin on first startup
- `mission_control_backend/app/main.py` — Mount auth router, protect existing endpoints
- `mission_control_backend/requirements.txt` — Add `bcrypt`, `python-jose[cryptography]`

**User Roles:**
- `admin` — Full access: manage users, all CRUD operations, system config
- `operator` — Can send missions, manage maps, view statistics
- `viewer` — Read-only: view dashboard, maps, missions, statistics

**Auth Flow:**
1. POST `/api/auth/login` with email/password → returns JWT access token + refresh token
2. Frontend stores tokens in localStorage
3. All API requests include `Authorization: Bearer <token>` header
4. Backend `Depends(get_current_user)` on protected routes
5. Role-based access via `Depends(require_role("admin"))` etc.

**Endpoints:**
- `POST /api/auth/login` — Login, returns tokens
- `POST /api/auth/refresh` — Refresh access token
- `GET /api/auth/me` — Current user profile
- `PUT /api/auth/me` — Update own profile/password
- `GET /api/auth/users` — List users (admin only)
- `POST /api/auth/users` — Create user (admin only)
- `PUT /api/auth/users/{id}` — Update user (admin only)
- `DELETE /api/auth/users/{id}` — Delete user (admin only)

**MongoDB Collection** `users`:
```json
{
  "_id": "ObjectId",
  "email": "string (unique)",
  "username": "string",
  "hashed_password": "string",
  "role": "admin | operator | viewer",
  "created_at": "datetime",
  "last_login": "datetime",
  "is_active": "boolean"
}
```

**Default admin bootstrap:** On startup, if no users exist, create admin from env vars (`ADMIN_EMAIL`, `ADMIN_PASSWORD`).

### 1B. Frontend Auth Integration

**Files to create/modify:**
- `webui/src/utils/auth.ts` — Token storage, auth state, axios interceptor
- `webui/src/pages/LoginPage.tsx` — Login form
- `webui/src/components/ProtectedRoute.tsx` — Route guard wrapper
- `webui/src/pages/UsersPage.tsx` — Admin user management page
- `webui/src/utils/api.ts` — Add auth headers to all fetch calls
- `webui/src/utils/ws.ts` — Add token to WebSocket connection
- `webui/src/App.tsx` — Add login route, protect routes, add Users nav item for admins
- `webui/src/main.tsx` — Auth initialization

**Auth State (Zustand):**
```typescript
{
  token: string | null,
  user: { id, email, username, role } | null,
  login: (email, password) => Promise<void>,
  logout: () => void,
  isAuthenticated: boolean
}
```

**UI Behavior:**
- Unauthenticated → redirect to `/login`
- Login page with email/password form, themed to match platform
- After login → redirect to Dashboard
- Nav shows user avatar/name + logout button
- Users page visible only for admins in nav
- Viewers see disabled mission-send buttons
- Token auto-refresh before expiry

### 1C. MQTT Access Key Security

**Files to modify:**
- `.env-template` — Add MQTT auth variables
- `docker-compose-robot.yml` — Configure Mosquitto with authentication
- `mission_control_backend/app/main.py` — Use MQTT credentials from env
- `ros_nodes/fiware_mqtt_bridge/config/fiware_config.yaml` — MQTT credentials
- `ros_nodes/fiware_mqtt_bridge/scripts/fiware_mqtt_bridge.py` — Use MQTT credentials
- `fiware_registration.py` — Use env-based API keys instead of hardcoded

**Steps:**
1. Add Mosquitto password file or ACL configuration to Docker setup
2. Configure IoT Agent to use MQTT username/password (already partially done in docker-compose)
3. Update backend MQTT client to authenticate
4. Update ROS bridge to authenticate with MQTT broker
5. Remove hardcoded API key from `fiware_registration.py`, use env var

---

## Phase 2: Statistics Dashboard

**Why second:** Uses existing mission data from Phase 1's protected API. No schema changes needed — aggregates from Orion/MongoDB.

### 2A. Backend Statistics API

**Files to create/modify:**
- `mission_control_backend/app/statistics/__init__.py`
- `mission_control_backend/app/statistics/router.py` — Statistics endpoints
- `mission_control_backend/app/statistics/aggregation.py` — MongoDB aggregation pipelines
- `mission_control_backend/app/main.py` — Mount statistics router

**Endpoints:**
- `GET /api/statistics/missions/summary` — Total counts by status (completed, failed, in_progress, cancelled)
- `GET /api/statistics/missions/over-time?period=day|week|month|year` — Missions per time period
- `GET /api/statistics/missions/duration` — Average/min/max mission duration
- `GET /api/statistics/robots/utilization` — Per-robot mission count, success rate, avg duration
- `GET /api/statistics/robots/activity` — Online hours per day/week
- `GET /api/statistics/overview` — Combined dashboard data in single request

**Data Sources:**
- Orion Context Broker entities (missions with timestamps)
- CrateDB via QuantumLeap (historical time-series data)
- Computed from `sentTime`, `executedTime`, `completedTime`, `status` fields on Mission entities

**Aggregation Examples:**
- Missions/day: Group by date truncation of `sentTime`
- Success rate: `completed / (completed + failed)` per robot
- Avg duration: `completedTime - executedTime` average
- Peak hours: Group by hour-of-day

### 2B. Frontend Statistics Page

**Files to create/modify:**
- `webui/src/pages/StatisticsPage.tsx` — Main statistics page
- `webui/src/utils/api.ts` — Add statistics fetch functions
- `webui/src/App.tsx` — Add Statistics nav item + route
- `webui/package.json` — Add `recharts` (lightweight charting library)

**Dashboard Layout:**
```
┌──────────────────────────────────────────────────┐
│  [Total Missions]  [Completed]  [Failed]  [Avg Duration]  │  ← KPI Cards / Gauges
├───────────────────────────┬──────────────────────┤
│  Missions Over Time       │  Success Rate Gauge  │  ← Line/Bar Chart + Gauge
│  (day/week/month/year)    │                      │
├───────────────────────────┼──────────────────────┤
│  Robot Utilization Table  │  Status Distribution │  ← Table + Pie/Donut Chart
│  (per-robot stats)        │  (pie chart)         │
├───────────────────────────┴──────────────────────┤
│  Mission Duration Histogram / Peak Hours Chart    │  ← Additional analytics
└──────────────────────────────────────────────────┘
```

**Charts (using Recharts):**
- **Line chart**: Missions over time with period selector (day/week/month/year)
- **Bar chart**: Completed vs failed per period
- **Donut/Pie chart**: Mission status distribution
- **Gauge**: Overall success rate percentage
- **Table**: Per-robot utilization with sparklines
- **Histogram**: Mission duration distribution

**Filters:**
- Date range picker
- Robot filter (select specific robot)
- Period granularity toggle (day/week/month/year)

---

## Phase 3: Parking Zones & Speed-Limit Zones

**Why third:** Builds on the map system. Zones are stored as map metadata and enforced during mission planning.

### 3A. Backend Zone Management

**Files to create/modify:**
- `mission_control_backend/app/zones/__init__.py`
- `mission_control_backend/app/zones/router.py` — Zone CRUD endpoints
- `mission_control_backend/app/zones/models.py` — Zone data models
- `mission_control_backend/app/main.py` — Mount zones router

**Zone Model:**
```python
class Zone(BaseModel):
    zoneId: str
    mapId: str  # Zone belongs to a specific map
    name: str
    zoneType: str  # "parking" or "speed_limit"
    polygon: List[List[float]]  # List of [x, y] vertices in EPSG:25832
    speedLimit: Optional[float] = None  # m/s, only for speed_limit zones
    color: Optional[str] = None  # Display color
    createdBy: Optional[str] = None  # User who created the zone
    createdAt: str
```

**Storage:** Orion Context Broker as NGSI-v2 entities (`type: "Zone"`) linked to map via `mapId`.

**Endpoints:**
- `GET /api/maps/{mapId}/zones` — List zones for a map
- `POST /api/maps/{mapId}/zones` — Create zone (operator+)
- `PUT /api/maps/{mapId}/zones/{zoneId}` — Update zone (operator+)
- `DELETE /api/maps/{mapId}/zones/{zoneId}` — Delete zone (operator+)

**Behavior:**
- Parking zones: Robot can be told to park here (used in advanced missions)
- Speed-limit zones: Stored and sent to robot with mission commands; robot bridge enforces speed
- Zone validation: Check polygon is valid (≥3 vertices, non-self-intersecting)

### 3B. Frontend Zone Drawing & Display

**Files to modify:**
- `webui/src/ui/MapView.tsx` — Add zone overlay rendering + drawing tools
- `webui/src/utils/state.ts` — Add zones state
- `webui/src/utils/api.ts` — Add zone API functions
- `webui/src/ui/RightPanel.tsx` — Add zone management panel/tab

**Leaflet Integration:**
- Render zones as colored polygons on the map (transparent fill + colored border)
- Parking zones: Blue with "P" label
- Speed-limit zones: Yellow/orange with speed value label
- Drawing mode: Click vertices to define polygon, double-click to close
- Edit mode: Drag vertices to reshape
- Delete: Click zone → confirm dialog

**UI:**
- Zone toggle button on map toolbar (show/hide zones)
- Drawing tool buttons: "Add Parking Zone", "Add Speed Zone"
- Zone properties panel (name, speed limit input for speed zones)
- Zone list in a collapsible sidebar section

### 3C. Robot Bridge Integration

**Files to modify:**
- `ros_nodes/fiware_mqtt_bridge/scripts/fiware_mqtt_bridge.py` — Parse zone data from commands
- Mission command enhancement: Include zone data when sending missions near/through zones

---

## Phase 4: Advanced Mission Scenarios

**Why fourth:** Builds on zones (parking) and existing mission system. Requires multi-waypoint support.

### 4A. Backend Multi-Waypoint Missions

**Files to modify:**
- `mission_control_backend/app/main.py` — New mission models, enhanced mission creation
- New models or extended existing:

**Enhanced Mission Model:**
```python
class MissionStep(BaseModel):
    stepId: str
    action: str  # "MOVE_TO", "WAIT", "PARK"
    waypoint: Optional[Point] = None  # For MOVE_TO
    duration: Optional[int] = None  # Seconds, for WAIT
    zoneId: Optional[str] = None  # For PARK (reference to parking zone)
    order: int  # Step sequence number

class AdvancedMissionRequest(BaseModel):
    robotId: str
    mapId: str
    name: Optional[str] = None  # Mission scenario name
    steps: List[MissionStep]
    # Optional: save as template
    saveAsTemplate: bool = False
    templateName: Optional[str] = None
```

**Mission Templates:**
- Store reusable mission scenarios in MongoDB
- `GET /api/mission-templates` — List templates
- `POST /api/mission-templates` — Save template
- `DELETE /api/mission-templates/{id}` — Delete template

**Endpoints:**
- `POST /api/missions/advanced` — Create multi-step mission
- `GET /api/mission-templates` — List saved templates

**Execution Flow:**
1. Backend creates mission entity with all steps
2. Sends first step command to robot
3. Robot completes step → reports via MQTT → backend sends next step
4. Repeat until all steps done or error occurs

### 4B. Frontend Mission Scenario Builder

**Files to modify:**
- `webui/src/ui/RightPanel.tsx` — Add "Advanced" tab with step builder
- `webui/src/ui/MapView.tsx` — Multi-point click mode, numbered waypoint markers
- `webui/src/utils/state.ts` — Add mission steps state
- `webui/src/utils/api.ts` — Add advanced mission + template API functions

**Step Builder UI:**
```
┌─ Advanced Mission ──────────────────┐
│  Mission Name: [________________]   │
│                                     │
│  Steps:                             │
│  ┌─ 1. MOVE_TO ──────────────────┐  │
│  │  X: 456789  Y: 5123456       │  │
│  │  [Up] [Down] [Remove]        │  │
│  └───────────────────────────────┘  │
│  ┌─ 2. WAIT ─────────────────────┐  │
│  │  Duration: [60] seconds       │  │
│  │  [Up] [Down] [Remove]        │  │
│  └───────────────────────────────┘  │
│  ┌─ 3. MOVE_TO ──────────────────┐  │
│  │  X: 456800  Y: 5123500       │  │
│  │  [Up] [Down] [Remove]        │  │
│  └───────────────────────────────┘  │
│  ┌─ 4. PARK ─────────────────────┐  │
│  │  Zone: Parking Zone A         │  │
│  │  [Up] [Down] [Remove]        │  │
│  └───────────────────────────────┘  │
│                                     │
│  [+ Add Step]  [Load Template]      │
│                                     │
│  [ ] Save as Template               │
│  [      Send Mission      ]        │
└─────────────────────────────────────┘
```

**Map Interaction:**
- Multi-click mode: Each click adds a numbered waypoint
- Waypoints shown as numbered markers (1, 2, 3...)
- Dashed lines connecting waypoints in order
- Click on parking zone to add "PARK" step
- Drag waypoints to reposition

### 4C. Robot Bridge Enhancement

**Files to modify:**
- `ros_nodes/fiware_mqtt_bridge/scripts/fiware_mqtt_bridge.py` — Multi-step command parsing, step-by-step execution with status reporting

---

## Phase 5: Map Generation Page

**Why last:** Most complex feature. Self-contained — doesn't block other features.

### 5A. Backend Map Generation

**Files to create/modify:**
- `mission_control_backend/app/mapgen/__init__.py`
- `mission_control_backend/app/mapgen/router.py` — Map generation endpoints
- `mission_control_backend/app/mapgen/generator.py` — Image generation, YAML creation
- `mission_control_backend/app/main.py` — Mount mapgen router

**Endpoints:**
- `GET /api/mapgen/crs-list` — List supported CRS codes (EPSG:25832, EPSG:4326, etc.)
- `POST /api/mapgen/generate` — Generate map from drawn occupancy grid
  - Body: `{ name, crs, origin, resolution, width, height, imageData (base64 PNG), zones? }`
  - Returns: Created map ID
- `POST /api/mapgen/from-region` — Generate blank map from geographic region
  - Body: `{ name, crs, bounds: { north, south, east, west }, resolution }`

**Generation Logic:**
1. Receive base64 PNG of drawn occupancy grid (white=free, black=occupied, grey=unknown)
2. Save as `map.png` in `maps/{mapId}/`
3. Generate `map.yaml` with:
   ```yaml
   image: map.png
   resolution: <from request>
   origin: [<x>, <y>, 0.0]
   negate: 0
   occupied_thresh: 0.65
   free_thresh: 0.196
   ```
4. Return map ID for immediate use

### 5B. Frontend Map Generation Page

**Files to create:**
- `webui/src/pages/MapGenPage.tsx` — Main map generation page

**Files to modify:**
- `webui/src/App.tsx` — Add MapGen route + nav item
- `webui/src/utils/api.ts` — Add map generation API functions

**Page Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  Map Generator                                              │
├─────────────────────────────────────────────────────────────┤
│  CRS: [EPSG:25832]   Region: [______________] [Search]      │
├──────────────────────────────────────────┬──────────────────┤
│                                          │ Drawing Tools:   │
│                                          │ ┌──────────────┐ │
│          Leaflet Map                     │ │  Free        │ │
│          (selected CRS)                  │ │  Occupied    │ │
│                                          │ │  Unknown     │ │
│          Draw occupancy grid             │ │  Eraser      │ │
│          on top of base map              │ ├──────────────┤ │
│                                          │ │ Brush: [5]px │ │
│                                          │ │ Shape: O / [] │ │
│                                          │ ├──────────────┤ │
│                                          │ │ Resolution:  │ │
│                                          │ │ [0.05] m/px  │ │
│                                          │ ├──────────────┤ │
│                                          │ │ Map Name:    │ │
│                                          │ │ [__________] │ │
│                                          │ │              │ │
│                                          │ │ [Save Map]   │ │
│                                          │ └──────────────┘ │
├──────────────────────────────────────────┴──────────────────┤
│  Preview: [Generated YAML content shown here]               │
└─────────────────────────────────────────────────────────────┘
```

**Implementation Approach:**
- **Canvas overlay on Leaflet**: Use HTML5 Canvas as a Leaflet layer for pixel-level drawing
- **Drawing tools**: Brush (circle/square), fill tool, eraser
- **Color mapping**: White (#FFFFFF) = free, Black (#000000) = occupied, Grey (#CDCDCD) = unknown
- **Address search**: Use Nominatim (OpenStreetMap) geocoding API for address lookup
- **CRS selection**: Dropdown with common CRS codes, updates map projection via proj4
- **Base map**: Optional tile layer (OSM) for reference while drawing, hidden during export
- **Export**: Canvas → PNG → base64 → POST to backend
- **Preview**: Show generated YAML content before saving

---

## Implementation Order Summary

| Phase | Feature | Est. Files | Dependencies |
|-------|---------|-----------|--------------|
| 1A | Backend Auth | ~10 new | None |
| 1B | Frontend Auth | ~5 new/mod | 1A |
| 1C | MQTT Security | ~5 mod | 1A |
| 2A | Backend Statistics | ~3 new | 1A (protected endpoints) |
| 2B | Frontend Statistics | ~2 new/mod | 2A |
| 3A | Backend Zones | ~3 new | 1A |
| 3B | Frontend Zones | ~4 mod | 3A |
| 3C | Robot Zone Integration | ~1 mod | 3A |
| 4A | Backend Advanced Missions | ~2 mod/new | 3A (parking zones) |
| 4B | Frontend Mission Builder | ~4 mod | 4A, 3B |
| 4C | Robot Multi-Step | ~1 mod | 4A |
| 5A | Backend Map Gen | ~3 new | 1A |
| 5B | Frontend Map Gen | ~2 new/mod | 5A |

---

## Verification Plan

### Phase 1 Testing
- Login with default admin credentials → get JWT token
- Create operator and viewer users → verify role restrictions
- Try accessing protected endpoints without token → 401
- Try operator accessing admin-only endpoints → 403
- Verify MQTT connection still works with credentials
- Test token refresh flow

### Phase 2 Testing
- Create several missions (completed, failed) → check statistics aggregation
- Verify charts render with real data
- Test period filters (day/week/month/year)
- Verify per-robot statistics are correct

### Phase 3 Testing
- Draw parking zone on map → save → verify appears on reload
- Draw speed-limit zone → verify speed value stored
- Delete zone → verify removed
- Verify zones display correctly with map overlay

### Phase 4 Testing
- Create multi-step mission: MOVE_TO → WAIT → MOVE_TO → PARK
- Verify steps sent sequentially to robot
- Save as template → reload → use template
- Verify numbered waypoints display on map

### Phase 5 Testing
- Select CRS → search address → map centers correctly
- Draw free/occupied/unknown areas with brush tools
- Enter name → save → map appears in Maps page
- Load generated map on Dashboard → verify coordinates align
