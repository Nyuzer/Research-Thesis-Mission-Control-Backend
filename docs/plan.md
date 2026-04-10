# Implementation Plan

## Phase 1: Authentication & Authorization + MQTT Security

- [x] 1A.1 — Create auth module structure (`auth/__init__.py`, `models.py`, `database.py`)
- [x] 1A.2 — Implement password hashing (`password.py`) and JWT handler (`jwt_handler.py`)
- [x] 1A.3 — Implement auth config, dependencies, and router (`config.py`, `dependencies.py`, `router.py`)
- [x] 1A.4 — Bootstrap default admin on startup (`bootstrap.py`) and mount auth router in `main.py`
- [x] 1A.5 — Protect existing backend endpoints with auth dependencies
- [x] 1B.1 — Create frontend auth utilities (`auth.ts`) and Zustand auth store
- [x] 1B.2 — Create LoginPage and ProtectedRoute components
- [x] 1B.3 — Create UsersPage (admin user management)
- [x] 1B.4 — Integrate auth into App.tsx, api.ts, ws.ts (headers, guards, nav)
- [x] 1C.1 — MQTT access key security (env vars, Mosquitto auth config, remove hardcoded keys)

## Phase 2: Statistics Dashboard

- [x] 2A.1 — Create backend statistics module (`statistics/__init__.py`, `router.py`, `aggregation.py`)
- [x] 2A.2 — Mount statistics router in main.py, protect with auth
- [x] 2B.1 — Create frontend StatisticsPage with charts (recharts)
- [x] 2B.2 — Add Statistics route and nav item to App.tsx

## Phase 3: Parking Zones & Speed-Limit Zones

- [x] 3A.1 — Create backend zones module (`zones/__init__.py`, `router.py`, `models.py`)
- [x] 3A.2 — Mount zones router in main.py, protect with auth
- [x] 3B.1 — Add zone overlay rendering and drawing tools to MapView.tsx
- [x] 3B.2 — Add zone management panel/tab in RightPanel.tsx + state + API
- [x] 3C.1 — Update ROS bridge to parse zone data from mission commands

## Phase 4: Advanced Mission Scenarios

- [x] 4A.1 — Backend multi-waypoint mission models and endpoints
- [x] 4A.2 — Backend mission templates CRUD
- [x] 4B.1 — Frontend mission scenario builder UI in RightPanel
- [x] 4B.2 — Multi-point click mode with numbered waypoints on MapView
- [x] 4C.1 — ROS bridge multi-step command parsing and execution

## Phase 5: Map Generation Page

- [x] 5A.1 — Backend map generation module (`mapgen/__init__.py`, `router.py`, `generator.py`)
- [x] 5A.2 — Mount mapgen router in main.py
- [x] 5B.1 — Create frontend MapGenPage with canvas drawing tools
- [x] 5B.2 — Add MapGen route and nav item to App.tsx

## Phase 6: Parking Zone Redesign & Map Overlay Controls

### Step 1 — OSM parking → occupied (backend)
- [x] 6.1 — Change `overpass.py` `_classify()`: `amenity=parking` → return `"occupied"` instead of `"parking"`

### Step 2 — Tooltip after OSM auto-fill (frontend MapGenPage)
- [x] 6.2 — After successful auto-fill, show info toast explaining parking is now obstacles

### Step 3 — Add `updateZone` API function (frontend)
- [x] 6.3 — Add `updateZone(mapId, zoneId, data)` to `api.ts`

### Step 4 — Goal point drag on main page (MapView)
- [x] 6.4 — Draggable goal points with point-in-polygon constraint on MapView

### Step 5 — Eye toggle button for overlay visibility (MapView)
- [x] 6.5 — Eye/EyeOff toggle button to hide/show entire SVG overlay
