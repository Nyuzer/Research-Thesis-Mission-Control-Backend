import { useRef, useState, useEffect, useCallback } from "react";
import L from "leaflet";
// @ts-ignore
import "proj4leaflet";
import proj4 from "proj4";
import { fetchJSON } from "@/utils/api";
import { showToast } from "@/lib/toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Paintbrush, Eraser, Square, Pentagon, Search, Save, Scan,
  MousePointer, Undo2, Redo2, Layers, MapPin, Gauge, ParkingSquare,
  Wand2, Trash2, MousePointerClick, Pencil, Eye, EyeOff,
} from "lucide-react";

/* ── proj4 + CRS ── */
proj4.defs(
  "EPSG:25832",
  "+proj=utm +zone=32 +ellps=GRS80 +units=m +no_defs +type=crs"
);

/* ── Types ── */
type ToolMode = "pan" | "brush" | "rectangle" | "polygon" | "eraser" | "pick" | "edit" | "bbox";
type OccupancyType = "free" | "occupied" | "unknown" | "parking" | "speed_limit";

interface DrawnFeature {
  id: string;
  tool: "brush" | "rectangle" | "polygon" | "eraser";
  occupancy: OccupancyType;
  latlngs: any[] | any[][]; // L.LatLng arrays
  brushRadius?: number; // meters, for brush strokes
  zoneName?: string;        // for parking/speed_limit zones
  goalPoint?: [number, number]; // for parking (lat, lng on map)
  isDefault?: boolean;      // for parking
  zoneSpeedLimit?: number;  // for speed_limit (m/s)
}

const NRW_CENTER: [number, number] = [51.45, 7.45]; // Dortmund area
const NRW_ZOOM = 13;

const OCCUPANCY_COLORS: Record<OccupancyType, { fill: string; stroke: string }> = {
  free:        { fill: "rgba(255,255,255,0.5)", stroke: "#ffffff" },
  occupied:    { fill: "rgba(0,0,0,0.5)",       stroke: "#000000" },
  unknown:     { fill: "rgba(200,200,200,0.5)", stroke: "#c8c8c8" },
  parking:     { fill: "rgba(59,130,246,0.45)", stroke: "#3b82f6" },
  speed_limit: { fill: "rgba(245,158,11,0.45)", stroke: "#f59e0b" },
};

const OCCUPANCY_PIXEL: Record<OccupancyType, [number, number, number]> = {
  free:        [254, 254, 254],
  occupied:    [0, 0, 0],
  unknown:     [205, 205, 205],
  parking:     [59, 130, 246],
  speed_limit: [245, 158, 11],
};

let _featureIdCounter = 0;
function nextId() { return `f_${++_featureIdCounter}`; }

/* ── Session persistence helpers ── */
const SS_KEY = "mapgen_state";

interface PersistedState {
  features: { id: string; tool: string; occupancy: string; latlngs: [number, number][]; brushRadius?: number; zoneName?: string; goalPoint?: [number, number]; isDefault?: boolean; zoneSpeedLimit?: number }[];
  bbox: { south: number; west: number; north: number; east: number } | null;
  mapName: string;
  resolution: string;
  brushSize: number;
  occupancy: string;
  baseLayer: string;
  mapView: { lat: number; lng: number; zoom: number };
}

function saveSession(s: PersistedState) {
  try { sessionStorage.setItem(SS_KEY, JSON.stringify(s)); } catch {}
}

function loadSession(): PersistedState | null {
  try {
    const raw = sessionStorage.getItem(SS_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function serializeFeatures(feats: DrawnFeature[]) {
  return feats.map((f) => ({
    id: f.id,
    tool: f.tool,
    occupancy: f.occupancy,
    latlngs: (f.latlngs as any[]).map((ll: any) => [ll.lat, ll.lng] as [number, number]),
    brushRadius: f.brushRadius,
    zoneName: f.zoneName,
    goalPoint: f.goalPoint,
    isDefault: f.isDefault,
    zoneSpeedLimit: f.zoneSpeedLimit,
  }));
}

function deserializeFeatures(raw: PersistedState["features"]): DrawnFeature[] {
  return raw.map((f) => ({
    id: f.id,
    tool: f.tool as DrawnFeature["tool"],
    occupancy: f.occupancy as OccupancyType,
    latlngs: f.latlngs.map(([lat, lng]: [number, number]) => L.latLng(lat, lng)),
    brushRadius: f.brushRadius,
    zoneName: f.zoneName,
    goalPoint: f.goalPoint,
    isDefault: f.isDefault,
    zoneSpeedLimit: f.zoneSpeedLimit,
  }));
}

/* ── Hit-testing helpers for object picking ── */
function pointInPolygon(px: number, py: number, pts: { x: number; y: number }[]): boolean {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const xi = pts[i].x, yi = pts[i].y;
    const xj = pts[j].x, yj = pts[j].y;
    if ((yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

function distToSegment(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax, dy = by - ay;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.hypot(px - ax, py - ay);
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / lenSq));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

function distToPolyline(px: number, py: number, pts: { x: number; y: number }[]): number {
  let min = Infinity;
  for (let i = 0; i < pts.length - 1; i++) {
    min = Math.min(min, distToSegment(px, py, pts[i].x, pts[i].y, pts[i + 1].x, pts[i + 1].y));
  }
  return min;
}

/* ═══════════════════════════ COMPONENT ═══════════════════════════ */

export default function MapGenPage() {
  /* ── Restore persisted session (lazy, runs once) ── */
  const savedRef = useRef(loadSession());

  /* ── Refs ── */
  const mapDivRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const bboxRectRef = useRef<any>(null);
  const tempLayerRef = useRef<any>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const cursorCircleRef = useRef<any>(null);
  const firstVertexMarkerRef = useRef<any>(null);
  const featuresRef = useRef<DrawnFeature[]>([]);

  /* ── State ── */
  const s = savedRef.current;
  const [tool, setTool] = useState<ToolMode>("pan");
  const [occupancy, setOccupancy] = useState<OccupancyType>((s?.occupancy as OccupancyType) || "occupied");
  const [brushSize, setBrushSize] = useState(s?.brushSize ?? 3);
  const [features, setFeatures] = useState<DrawnFeature[]>(() => s?.features ? deserializeFeatures(s.features) : []);
  const [bbox, setBbox] = useState<any>(() => s?.bbox ? L.latLngBounds([s.bbox.south, s.bbox.west], [s.bbox.north, s.bbox.east]) : null);
  const [mapName, setMapName] = useState(s?.mapName ?? "");
  const [resolution, setResolution] = useState(s?.resolution ?? "0.1");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);
  const [osmLoading, setOsmLoading] = useState(false);
  const [osmCooldown, setOsmCooldown] = useState(0);
  const [baseLayer, setBaseLayer] = useState<"osm" | "ortho">((s?.baseLayer as "osm" | "ortho") || "osm");
  const [polyVertexCount, setPolyVertexCount] = useState(0);
  // Undo/redo: snapshot-based history
  const [undoStack, setUndoStack] = useState<DrawnFeature[][]>([]);
  const [redoStack, setRedoStack] = useState<DrawnFeature[][]>([]);
  const [selectedFeatureId, setSelectedFeatureId] = useState<string | null>(null);
  const [settingGoalPoint, setSettingGoalPoint] = useState(false);
  const [editFeatureId, setEditFeatureId] = useState<string | null>(null);
  const [canvasVisible, setCanvasVisible] = useState(true);
  const editFeatureIdRef = useRef<string | null>(null);
  editFeatureIdRef.current = editFeatureId;
  const editDragRef = useRef<{ vertexIdx: number; featureId: string } | null>(null);

  // Escape key cancels goal point mode
  useEffect(() => {
    if (!settingGoalPoint) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setSettingGoalPoint(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [settingGoalPoint]);

  // Drawing state (not in React state for performance)
  const drawingRef = useRef(false);
  const currentStrokeRef = useRef<any[]>([]);
  const polyVerticesRef = useRef<any[]>([]);

  // Keep featuresRef in sync
  featuresRef.current = features;

  /* ── Helper: meters per pixel at current zoom ── */
  function getMetersPerPixel() {
    const map = mapRef.current;
    if (!map) return 1;
    const center = map.getCenter();
    const zoom = map.getZoom();
    return 40075016.686 * Math.cos((center.lat * Math.PI) / 180) / Math.pow(2, zoom + 8);
  }

  /* ── Canvas rendering function ── */
  const renderCanvas = useCallback(() => {
    const map = mapRef.current;
    const canvas = overlayCanvasRef.current;
    if (!map || !canvas) return;

    // Sync internal resolution with CSS size
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (w === 0 || h === 0) return;
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, w, h);

    const mpp = getMetersPerPixel();
    const feats = featuresRef.current;

    for (const f of feats) {
      const isEraser = f.tool === "eraser";
      ctx.globalCompositeOperation = isEraser ? "destination-out" : "source-over";

      if (isEraser) {
        ctx.fillStyle = "rgba(0,0,0,1)";
        ctx.strokeStyle = "rgba(0,0,0,1)";
      } else {
        ctx.fillStyle = OCCUPANCY_COLORS[f.occupancy].fill;
        ctx.strokeStyle = OCCUPANCY_COLORS[f.occupancy].stroke;
      }

      if (f.tool === "brush" || f.tool === "eraser") {
        const pts = f.latlngs as any[];
        const radiusPx = (f.brushRadius || 3) / mpp;

        if (pts.length === 1) {
          const p = map.latLngToContainerPoint(pts[0]);
          ctx.beginPath();
          ctx.arc(p.x, p.y, radiusPx, 0, Math.PI * 2);
          ctx.fill();
        } else {
          ctx.lineWidth = radiusPx * 2;
          ctx.lineCap = "round";
          ctx.lineJoin = "round";
          ctx.beginPath();
          const first = map.latLngToContainerPoint(pts[0]);
          ctx.moveTo(first.x, first.y);
          for (let i = 1; i < pts.length; i++) {
            const p = map.latLngToContainerPoint(pts[i]);
            ctx.lineTo(p.x, p.y);
          }
          ctx.stroke();
        }
      } else if (f.tool === "rectangle") {
        const corners = f.latlngs as any[];
        const p1 = map.latLngToContainerPoint(corners[0]);
        const p2 = map.latLngToContainerPoint(corners[1]);
        const rx = Math.min(p1.x, p2.x), ry = Math.min(p1.y, p2.y);
        const rw = Math.abs(p2.x - p1.x), rh = Math.abs(p2.y - p1.y);
        ctx.fillRect(rx, ry, rw, rh);
        ctx.lineWidth = 2;
        ctx.strokeRect(rx, ry, rw, rh);
      } else if (f.tool === "polygon") {
        const pts = f.latlngs as any[];
        if (pts.length >= 3) {
          ctx.beginPath();
          const first = map.latLngToContainerPoint(pts[0]);
          ctx.moveTo(first.x, first.y);
          for (let i = 1; i < pts.length; i++) {
            const p = map.latLngToContainerPoint(pts[i]);
            ctx.lineTo(p.x, p.y);
          }
          ctx.closePath();
          ctx.fill();
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      }
    }

    ctx.globalCompositeOperation = "source-over";

    // Draw zone name labels at centroid
    for (const f of feats) {
      if ((f.occupancy !== "parking" && f.occupancy !== "speed_limit") || !f.zoneName) continue;
      let cx = 0, cy = 0, n = 0;
      if (f.tool === "polygon") {
        const pts = f.latlngs as any[];
        for (const ll of pts) { const p = map.latLngToContainerPoint(ll); cx += p.x; cy += p.y; n++; }
      } else if (f.tool === "rectangle") {
        const corners = f.latlngs as any[];
        const p1 = map.latLngToContainerPoint(corners[0]);
        const p2 = map.latLngToContainerPoint(corners[1]);
        cx = (p1.x + p2.x) / 2; cy = (p1.y + p2.y) / 2; n = 1;
      }
      if (n === 0) continue;
      if (n > 1) { cx /= n; cy /= n; }
      const color = f.occupancy === "parking" ? "#3b82f6" : "#f59e0b";
      const prefix = f.occupancy === "parking" ? "P" : "S";
      const defaultStar = f.isDefault ? " \u2605" : "";
      const label = `${prefix}: ${f.zoneName}${defaultStar}`;
      ctx.font = "bold 11px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.strokeStyle = "#0f172a";
      ctx.lineWidth = 3;
      ctx.lineJoin = "round";
      ctx.strokeText(label, cx, cy);
      ctx.fillStyle = color;
      ctx.fillText(label, cx, cy);
    }

    // Draw goal point markers for parking zones
    for (const f of feats) {
      if (f.occupancy === "parking" && f.goalPoint) {
        const gpLL = L.latLng(f.goalPoint[0], f.goalPoint[1]);
        const p = map.latLngToContainerPoint(gpLL);
        if (!isFinite(p.x) || !isFinite(p.y)) continue;
        // Green crosshair
        ctx.strokeStyle = "#22c55e";
        ctx.lineWidth = 2;
        ctx.lineCap = "round";
        ctx.beginPath(); ctx.moveTo(p.x - 8, p.y); ctx.lineTo(p.x - 3, p.y); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(p.x + 3, p.y); ctx.lineTo(p.x + 8, p.y); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(p.x, p.y - 8); ctx.lineTo(p.x, p.y - 3); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(p.x, p.y + 3); ctx.lineTo(p.x, p.y + 8); ctx.stroke();
        ctx.fillStyle = "#22c55e";
        ctx.beginPath(); ctx.arc(p.x, p.y, 3, 0, Math.PI * 2); ctx.fill();
        // Label
        ctx.font = "bold 9px Inter, sans-serif";
        ctx.fillStyle = "#22c55e";
        ctx.strokeStyle = "#0f172a";
        ctx.lineWidth = 2.5;
        ctx.textAlign = "center";
        ctx.strokeText("GOAL", p.x, p.y - 12);
        ctx.fillText("GOAL", p.x, p.y - 12);
      }
    }

    // Draw vertex handles for feature being edited
    const eid = editFeatureIdRef.current;
    if (eid) {
      const ef = feats.find((f) => f.id === eid);
      if (ef) {
        let verts: any[] = [];
        if (ef.tool === "polygon") {
          verts = ef.latlngs as any[];
        } else if (ef.tool === "rectangle") {
          const c = ef.latlngs as any[];
          verts = [c[0], L.latLng(c[0].lat, c[1].lng), c[1], L.latLng(c[1].lat, c[0].lng)];
        } else if (ef.tool === "brush" || ef.tool === "eraser") {
          verts = ef.latlngs as any[];
        }
        for (const ll of verts) {
          const p = map.latLngToContainerPoint(ll);
          if (!isFinite(p.x) || !isFinite(p.y)) continue;
          ctx.fillStyle = "#ffffff";
          ctx.strokeStyle = "#22d3ee";
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
        }
      }
    }
  }, []);

  /* ── Initialize Leaflet ── */
  useEffect(() => {
    if (!mapDivRef.current || mapRef.current) return;

    const sv = savedRef.current?.mapView;
    const map = L.map(mapDivRef.current, {
      center: sv ? [sv.lat, sv.lng] : NRW_CENTER,
      zoom: sv?.zoom ?? NRW_ZOOM,
      zoomControl: true,
    });

    // OSM base layer
    const osmLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
      maxZoom: 19,
    });

    // NRW Orthophoto WMS
    const orthoLayer = (L as any).tileLayer.wms("https://www.wms.nrw.de/geobasis/wms_nw_dop", {
      layers: "nw_dop_rgb",
      format: "image/png",
      transparent: true,
      attribution: "&copy; Land NRW",
      maxZoom: 20,
    });

    osmLayer.addTo(map);
    (map as any)._osmLayer = osmLayer;
    (map as any)._orthoLayer = orthoLayer;

    // Canvas overlay inside map container, above tiles but below controls
    const canvas = document.createElement("canvas");
    canvas.style.position = "absolute";
    canvas.style.top = "0";
    canvas.style.left = "0";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    canvas.style.zIndex = "401";
    canvas.style.pointerEvents = "none";
    map.getContainer().appendChild(canvas);
    overlayCanvasRef.current = canvas;

    mapRef.current = map;

    return () => {
      if (overlayCanvasRef.current?.parentNode) {
        overlayCanvasRef.current.parentNode.removeChild(overlayCanvasRef.current);
      }
      overlayCanvasRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  /* ── Toggle canvas visibility ── */
  useEffect(() => {
    const canvas = overlayCanvasRef.current;
    if (canvas) canvas.style.display = canvasVisible ? "block" : "none";
  }, [canvasVisible]);

  /* ── Canvas re-render on map events ── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    let rafId = 0;
    const onMapChange = () => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(renderCanvas);
    };

    map.on("move", onMapChange);
    map.on("zoom", onMapChange);
    map.on("resize", onMapChange);

    return () => {
      cancelAnimationFrame(rafId);
      map.off("move", onMapChange);
      map.off("zoom", onMapChange);
      map.off("resize", onMapChange);
    };
  }, [renderCanvas]);

  /* ── Re-render canvas when features change ── */
  useEffect(() => {
    renderCanvas();
  }, [features, renderCanvas]);

  /* ── Persist state to sessionStorage ── */
  useEffect(() => {
    const map = mapRef.current;
    const center = map?.getCenter();
    const zoom = map?.getZoom();
    saveSession({
      features: serializeFeatures(features),
      bbox: bbox ? { south: bbox.getSouth(), west: bbox.getWest(), north: bbox.getNorth(), east: bbox.getEast() } : null,
      mapName,
      resolution,
      brushSize,
      occupancy,
      baseLayer,
      mapView: center ? { lat: center.lat, lng: center.lng, zoom: zoom ?? NRW_ZOOM } : { lat: NRW_CENTER[0], lng: NRW_CENTER[1], zoom: NRW_ZOOM },
    });
  }, [features, bbox, mapName, resolution, brushSize, occupancy, baseLayer]);

  /* ── Persist map view on move/zoom ── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const persist = () => {
      const c = map.getCenter();
      const prev = loadSession();
      if (prev) { prev.mapView = { lat: c.lat, lng: c.lng, zoom: map.getZoom() }; saveSession(prev); }
    };
    map.on("moveend", persist);
    map.on("zoomend", persist);
    return () => { map.off("moveend", persist); map.off("zoomend", persist); };
  }, []);

  /* ── Switch base layer ── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const osm = (map as any)._osmLayer;
    const ortho = (map as any)._orthoLayer;
    if (baseLayer === "osm") {
      if (!map.hasLayer(osm)) osm.addTo(map);
      if (map.hasLayer(ortho)) map.removeLayer(ortho);
    } else {
      if (!map.hasLayer(ortho)) ortho.addTo(map);
      if (map.hasLayer(osm)) map.removeLayer(osm);
    }
  }, [baseLayer]);

  /* ── Re-render bbox ── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (bboxRectRef.current) {
      map.removeLayer(bboxRectRef.current);
      bboxRectRef.current = null;
    }
    if (bbox) {
      bboxRectRef.current = L.rectangle(bbox, {
        color: "#22d3ee",
        weight: 3,
        fill: false,
        dashArray: "8 4",
      }).addTo(map);
    }
  }, [bbox]);

  /* ── Cursor style based on tool ── */
  useEffect(() => {
    const el = mapDivRef.current;
    if (!el) return;
    const cursors: Record<ToolMode, string> = {
      pan: "grab",
      brush: "crosshair",
      rectangle: "crosshair",
      polygon: "crosshair",
      eraser: "crosshair",
      pick: "pointer",
      edit: "pointer",
      bbox: "crosshair",
    };
    el.style.cursor = cursors[tool] || "default";
  }, [tool]);

  /* ── Disable map drag when drawing ── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (tool === "pan" || tool === "pick" || tool === "edit") {
      map.dragging.enable();
      map.doubleClickZoom.enable();
    } else {
      map.dragging.disable();
      map.doubleClickZoom.disable();
    }
  }, [tool]);

  // Push current state to undo stack before any mutation
  const pushUndo = useCallback(() => {
    setUndoStack((us) => [...us.slice(-50), featuresRef.current]);
    setRedoStack([]);
  }, []);

  // Add/modify features (used for drawing new shapes)
  const addFeatures = useCallback((fn: (prev: DrawnFeature[]) => DrawnFeature[]) => {
    pushUndo();
    setFeatures(fn);
  }, [pushUndo]);

  // Remove a feature by index
  const removeFeature = useCallback((idx: number) => {
    const feats = featuresRef.current;
    if (idx < 0 || idx >= feats.length) return;
    pushUndo();
    setFeatures(feats.filter((_, i) => i !== idx));
  }, [pushUndo]);

  /* ── Map mouse events for drawing ── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const SNAP_DIST_PX = 12; // px threshold to snap to first vertex

    function cleanupPolyPreview() {
      if (tempLayerRef.current) { map.removeLayer(tempLayerRef.current); tempLayerRef.current = null; }
      if (firstVertexMarkerRef.current) { map.removeLayer(firstVertexMarkerRef.current); firstVertexMarkerRef.current = null; }
    }

    function onMouseDown(e: any) {
      if (tool === "pan") return;

      // Edit mode: start dragging a vertex
      if (tool === "edit" && editFeatureIdRef.current) {
        const clickPx = map.latLngToContainerPoint(e.latlng);
        const ef = featuresRef.current.find((f) => f.id === editFeatureIdRef.current);
        if (ef) {
          let verts: any[] = [];
          if (ef.tool === "polygon") verts = ef.latlngs as any[];
          else if (ef.tool === "rectangle") {
            const c = ef.latlngs as any[];
            verts = [c[0], c[1]]; // only the 2 corner points are editable
          } else if (ef.tool === "brush" || ef.tool === "eraser") verts = ef.latlngs as any[];

          for (let i = 0; i < verts.length; i++) {
            const vPx = map.latLngToContainerPoint(verts[i]);
            if (Math.hypot(clickPx.x - vPx.x, clickPx.y - vPx.y) <= 8) {
              editDragRef.current = { vertexIdx: i, featureId: ef.id };
              pushUndo();
              map.dragging.disable();
              e.originalEvent?.preventDefault?.();
              return;
            }
          }
        }
      }

      if (tool === "brush" || tool === "eraser") {
        drawingRef.current = true;
        currentStrokeRef.current = [e.latlng];
      } else if (tool === "rectangle" || tool === "bbox") {
        drawingRef.current = true;
        currentStrokeRef.current = [e.latlng];
      }
    }

    function onMouseMove(e: any) {
      // Edit mode: drag vertex
      if (editDragRef.current) {
        const { vertexIdx, featureId } = editDragRef.current;
        const feats = featuresRef.current;
        const updated = feats.map((f) => {
          if (f.id !== featureId) return f;
          const newLatlngs = [...(f.latlngs as any[])];
          newLatlngs[vertexIdx] = e.latlng;
          return { ...f, latlngs: newLatlngs };
        });
        featuresRef.current = updated;
        renderCanvas();
        return;
      }

      // Brush/eraser cursor circle
      if (tool === "brush" || tool === "eraser") {
        if (cursorCircleRef.current) map.removeLayer(cursorCircleRef.current);
        cursorCircleRef.current = L.circle(e.latlng, {
          radius: brushSize,
          color: tool === "eraser" ? "#ef4444" : OCCUPANCY_COLORS[occupancy].stroke,
          weight: 1.5,
          fillOpacity: 0.08,
          fill: true,
          dashArray: "4 4",
          interactive: false,
        }).addTo(map);
      }

      // Polygon live preview: line from vertices to cursor
      if (tool === "polygon" && polyVerticesRef.current.length > 0) {
        if (tempLayerRef.current) map.removeLayer(tempLayerRef.current);

        const verts = polyVerticesRef.current;
        const previewPts = [...verts, e.latlng];

        if (verts.length >= 3) {
          // Show closed polygon preview
          tempLayerRef.current = L.polygon(previewPts, {
            color: OCCUPANCY_COLORS[occupancy].stroke,
            fillColor: OCCUPANCY_COLORS[occupancy].fill,
            fillOpacity: 0.25,
            weight: 2,
            dashArray: "6 3",
          }).addTo(map);
        } else {
          // Show polyline preview
          tempLayerRef.current = L.polyline(previewPts, {
            color: OCCUPANCY_COLORS[occupancy].stroke,
            weight: 2,
            dashArray: "6 3",
          }).addTo(map);
        }

        // First-vertex snap indicator
        if (firstVertexMarkerRef.current) map.removeLayer(firstVertexMarkerRef.current);
        if (verts.length >= 3) {
          const firstPx = map.latLngToContainerPoint(verts[0]);
          const cursorPx = map.latLngToContainerPoint(e.latlng);
          const isNear = firstPx.distanceTo(cursorPx) < SNAP_DIST_PX;
          firstVertexMarkerRef.current = L.circleMarker(verts[0], {
            radius: isNear ? 10 : 6,
            color: isNear ? "#22d3ee" : OCCUPANCY_COLORS[occupancy].stroke,
            fillColor: isNear ? "#22d3ee" : "#fff",
            fillOpacity: isNear ? 0.6 : 0.4,
            weight: 2,
            interactive: false,
          }).addTo(map);
        }
      }

      if (!drawingRef.current) return;

      if (tool === "brush" || tool === "eraser") {
        currentStrokeRef.current.push(e.latlng);
        if (tempLayerRef.current) map.removeLayer(tempLayerRef.current);
        tempLayerRef.current = L.polyline(currentStrokeRef.current, {
          color: tool === "eraser" ? "#ef4444" : OCCUPANCY_COLORS[occupancy].stroke,
          weight: brushSize * 2 / getMetersPerPixel(),
          opacity: tool === "eraser" ? 0.4 : 0.5,
          dashArray: tool === "eraser" ? "6 3" : undefined,
        }).addTo(map);
      } else if (tool === "rectangle" || tool === "bbox") {
        if (tempLayerRef.current) map.removeLayer(tempLayerRef.current);
        const bounds = L.latLngBounds(currentStrokeRef.current[0], e.latlng);
        const color = tool === "bbox" ? "#22d3ee" : OCCUPANCY_COLORS[occupancy].stroke;
        tempLayerRef.current = L.rectangle(bounds, {
          color,
          weight: 2,
          fillOpacity: tool === "bbox" ? 0.1 : 0.3,
          dashArray: tool === "bbox" ? "8 4" : undefined,
        }).addTo(map);
      }
    }

    function onMouseUp(e: any) {
      // Finalize vertex drag
      if (editDragRef.current) {
        const { vertexIdx, featureId } = editDragRef.current;
        editDragRef.current = null;
        map.dragging.enable();
        // Commit the updated latlngs to React state
        setFeatures((prev) =>
          prev.map((f) => {
            if (f.id !== featureId) return f;
            const newLatlngs = [...(f.latlngs as any[])];
            newLatlngs[vertexIdx] = e.latlng;
            return { ...f, latlngs: newLatlngs };
          })
        );
        return;
      }

      if (!drawingRef.current) return;
      drawingRef.current = false;
      if (tempLayerRef.current && tool !== "polygon") {
        map.removeLayer(tempLayerRef.current);
        tempLayerRef.current = null;
      }

      if (tool === "brush" || tool === "eraser") {
        const pts = currentStrokeRef.current;
        if (pts.length > 0) {
          const occ = tool === "eraser" ? "unknown" : occupancy;
          const featureTool = tool === "eraser" ? "eraser" as const : "brush" as const;
          addFeatures((prev) => [
            ...prev,
            { id: nextId(), tool: featureTool, occupancy: occ, latlngs: [...pts], brushRadius: brushSize },
          ]);
        }
        currentStrokeRef.current = [];
      } else if (tool === "rectangle") {
        const start = currentStrokeRef.current[0];
        if (start) {
          addFeatures((prev) => [
            ...prev,
            { id: nextId(), tool: "rectangle", occupancy, latlngs: [start, e.latlng] },
          ]);
        }
        currentStrokeRef.current = [];
      } else if (tool === "bbox") {
        const start = currentStrokeRef.current[0];
        if (start) {
          setBbox(L.latLngBounds(start, e.latlng));
        }
        currentStrokeRef.current = [];
        setTool("pan");
      }
    }

    function onClick(e: any) {
      // ── Goal point placement mode ──
      if (settingGoalPoint && selectedFeatureId) {
        const ll = e.latlng;
        setFeatures((prev) =>
          prev.map((f) =>
            f.id === selectedFeatureId ? { ...f, goalPoint: [ll.lat, ll.lng] as [number, number] } : f
          )
        );
        setSettingGoalPoint(false);
        renderCanvas();
        return;
      }

      // ── Edit mode: click to select feature for vertex editing ──
      if (tool === "edit") {
        const clickPx = map.latLngToContainerPoint(e.latlng);
        const feats = featuresRef.current;
        const mpp = getMetersPerPixel();
        // Walk backwards: topmost first
        for (let i = feats.length - 1; i >= 0; i--) {
          const f = feats[i];
          let hit = false;
          if (f.tool === "polygon") {
            const pts = (f.latlngs as any[]).map((ll: any) => map.latLngToContainerPoint(ll));
            hit = pointInPolygon(clickPx.x, clickPx.y, pts);
          } else if (f.tool === "brush" || f.tool === "eraser") {
            const pts = (f.latlngs as any[]).map((ll: any) => map.latLngToContainerPoint(ll));
            const radiusPx = (f.brushRadius || 3) / mpp;
            const dist = pts.length === 1
              ? Math.hypot(clickPx.x - pts[0].x, clickPx.y - pts[0].y)
              : distToPolyline(clickPx.x, clickPx.y, pts);
            hit = dist <= radiusPx + 4;
          } else if (f.tool === "rectangle") {
            const corners = f.latlngs as any[];
            const p1 = map.latLngToContainerPoint(corners[0]);
            const p2 = map.latLngToContainerPoint(corners[1]);
            hit = clickPx.x >= Math.min(p1.x, p2.x) && clickPx.x <= Math.max(p1.x, p2.x) &&
                  clickPx.y >= Math.min(p1.y, p2.y) && clickPx.y <= Math.max(p1.y, p2.y);
          }
          if (hit) {
            setEditFeatureId(f.id);
            renderCanvas();
            return;
          }
        }
        // Clicked on empty space — deselect
        setEditFeatureId(null);
        renderCanvas();
        return;
      }

      // ── Object picker: click to delete a feature ──
      if (tool === "pick") {
        const clickPx = map.latLngToContainerPoint(e.latlng);
        const feats = featuresRef.current;
        const mpp = getMetersPerPixel();
        // Walk backwards so topmost (last drawn) feature is picked first
        for (let i = feats.length - 1; i >= 0; i--) {
          const f = feats[i];
          if (f.tool === "polygon") {
            const pts = (f.latlngs as any[]).map((ll: any) => map.latLngToContainerPoint(ll));
            if (pointInPolygon(clickPx.x, clickPx.y, pts)) {
              removeFeature(i);
              return;
            }
          } else if (f.tool === "brush" || f.tool === "eraser") {
            const pts = (f.latlngs as any[]).map((ll: any) => map.latLngToContainerPoint(ll));
            const radiusPx = (f.brushRadius || 3) / mpp;
            const dist = pts.length === 1
              ? Math.hypot(clickPx.x - pts[0].x, clickPx.y - pts[0].y)
              : distToPolyline(clickPx.x, clickPx.y, pts);
            if (dist <= radiusPx + 4) {
              removeFeature(i);
              return;
            }
          } else if (f.tool === "rectangle") {
            const corners = f.latlngs as any[];
            const p1 = map.latLngToContainerPoint(corners[0]);
            const p2 = map.latLngToContainerPoint(corners[1]);
            const minX = Math.min(p1.x, p2.x), maxX = Math.max(p1.x, p2.x);
            const minY = Math.min(p1.y, p2.y), maxY = Math.max(p1.y, p2.y);
            if (clickPx.x >= minX && clickPx.x <= maxX && clickPx.y >= minY && clickPx.y <= maxY) {
              removeFeature(i);
              return;
            }
          }
        }
        return;
      }

      if (tool !== "polygon") return;

      const verts = polyVerticesRef.current;

      // If >= 3 vertices and click is near the first vertex → close polygon
      if (verts.length >= 3) {
        const firstPx = map.latLngToContainerPoint(verts[0]);
        const clickPx = map.latLngToContainerPoint(e.latlng);
        if (firstPx.distanceTo(clickPx) < SNAP_DIST_PX) {
          // Copy latlngs BEFORE clearing — addFeatures callback runs async
          const latlngs = [...verts];
          verts.length = 0;
          addFeatures((prev) => [
            ...prev,
            { id: nextId(), tool: "polygon", occupancy, latlngs },
          ]);
          setPolyVertexCount(0);
          cleanupPolyPreview();
          return;
        }
      }

      // Otherwise add vertex
      verts.push(e.latlng);
      setPolyVertexCount(verts.length);

      // Show first-vertex marker starting from vertex 1
      if (verts.length === 1) {
        if (firstVertexMarkerRef.current) map.removeLayer(firstVertexMarkerRef.current);
        firstVertexMarkerRef.current = L.circleMarker(verts[0], {
          radius: 6,
          color: OCCUPANCY_COLORS[occupancy].stroke,
          fillColor: "#fff",
          fillOpacity: 0.4,
          weight: 2,
          interactive: false,
        }).addTo(map);
      }
    }

    map.on("mousedown", onMouseDown);
    map.on("mousemove", onMouseMove);
    map.on("mouseup", onMouseUp);
    map.on("click", onClick);

    return () => {
      map.off("mousedown", onMouseDown);
      map.off("mousemove", onMouseMove);
      map.off("mouseup", onMouseUp);
      map.off("click", onClick);
      if (cursorCircleRef.current) { map.removeLayer(cursorCircleRef.current); cursorCircleRef.current = null; }
      cleanupPolyPreview();
    };
  }, [tool, occupancy, brushSize, addFeatures, pushUndo, settingGoalPoint, selectedFeatureId, editFeatureId]);

  /* ── Geocoding search (Nominatim) ── */
  const searchTimeoutRef = useRef<any>(null);
  const doSearch = useCallback(() => {
    if (!searchQuery.trim()) { setSearchResults([]); return; }
    clearTimeout(searchTimeoutRef.current);
    searchTimeoutRef.current = setTimeout(async () => {
      try {
        const q = encodeURIComponent(searchQuery);
        const resp = await fetch(
          `https://nominatim.openstreetmap.org/search?q=${q}&format=json&countrycodes=de&viewbox=5.8,50.3,9.5,52.6&bounded=1&limit=5`,
          { headers: { "User-Agent": "MissionControlMapGen/1.0" } }
        );
        const data = await resp.json();
        setSearchResults(data);
      } catch {
        setSearchResults([]);
      }
    }, 600);
  }, [searchQuery]);

  useEffect(() => { doSearch(); }, [searchQuery, doSearch]);

  const panToResult = (r: any) => {
    const map = mapRef.current;
    if (!map) return;
    map.setView([parseFloat(r.lat), parseFloat(r.lon)], 17);
    setSearchResults([]);
    setSearchQuery(r.display_name.split(",").slice(0, 2).join(","));
  };

  /* ── Undo / Redo ── */
  const undo = () => {
    // If placing polygon vertices, undo removes last vertex
    if (tool === "polygon" && polyVerticesRef.current.length > 0) {
      polyVerticesRef.current.pop();
      setPolyVertexCount(polyVerticesRef.current.length);
      const map = mapRef.current;
      if (map) {
        if (tempLayerRef.current) { map.removeLayer(tempLayerRef.current); tempLayerRef.current = null; }
        if (firstVertexMarkerRef.current) { map.removeLayer(firstVertexMarkerRef.current); firstVertexMarkerRef.current = null; }
      }
      return;
    }
    if (undoStack.length === 0) return;
    const prevState = undoStack[undoStack.length - 1];
    setUndoStack((us) => us.slice(0, -1));
    setRedoStack((rs) => [...rs, featuresRef.current]);
    setFeatures(prevState);
  };

  const redo = () => {
    if (redoStack.length === 0) return;
    const nextState = redoStack[redoStack.length - 1];
    setRedoStack((rs) => rs.slice(0, -1));
    setUndoStack((us) => [...us, featuresRef.current]);
    setFeatures(nextState);
  };

  /* ── Clear all ── */
  const clearAll = () => {
    pushUndo();
    setFeatures([]);
    polyVerticesRef.current = [];
    setPolyVertexCount(0);
    const map = mapRef.current;
    if (map) {
      if (tempLayerRef.current) { map.removeLayer(tempLayerRef.current); tempLayerRef.current = null; }
      if (firstVertexMarkerRef.current) { map.removeLayer(firstVertexMarkerRef.current); firstVertexMarkerRef.current = null; }
    }
  };

  /* ── Export: rasterize to PNG and save ── */
  const exportMap = async () => {
    if (!bbox) { showToast("Draw a bounding box first", "warning"); return; }
    if (!mapName.trim()) { showToast("Enter a map name", "warning"); return; }

    setSaving(true);
    try {
      const res = parseFloat(resolution) || 0.1;

      // Convert bbox to EPSG:25832
      const sw = bbox.getSouthWest();
      const ne = bbox.getNorthEast();
      const [swX, swY] = proj4("EPSG:4326", "EPSG:25832", [sw.lng, sw.lat]);
      const [neX, neY] = proj4("EPSG:4326", "EPSG:25832", [ne.lng, ne.lat]);

      const widthM = neX - swX;
      const heightM = neY - swY;
      const widthPx = Math.ceil(widthM / res);
      const heightPx = Math.ceil(heightM / res);

      if (widthPx > 4096 || heightPx > 4096) {
        showToast(`Map too large (${widthPx}x${heightPx}px). Reduce area or increase resolution.`, "error");
        setSaving(false);
        return;
      }

      // Create offscreen canvas
      const canvas = document.createElement("canvas");
      canvas.width = widthPx;
      canvas.height = heightPx;
      const ctx = canvas.getContext("2d")!;

      // Fill with unknown (grey)
      ctx.fillStyle = `rgb(205,205,205)`;
      ctx.fillRect(0, 0, widthPx, heightPx);

      // Helper: latlng → pixel on canvas
      function toPixel(ll: any): [number, number] {
        const [x, y] = proj4("EPSG:4326", "EPSG:25832", [ll.lng, ll.lat]);
        const px = (x - swX) / res;
        const py = heightPx - (y - swY) / res; // Y flipped
        return [px, py];
      }

      // Draw each feature
      for (const f of features) {
        const [r, g, b] = OCCUPANCY_PIXEL[f.occupancy];
        ctx.fillStyle = `rgb(${r},${g},${b})`;
        ctx.strokeStyle = `rgb(${r},${g},${b})`;

        if (f.tool === "brush" || f.tool === "eraser") {
          const pts = f.latlngs as any[];
          const radiusPx = (f.brushRadius || brushSize) / res;
          ctx.lineWidth = radiusPx * 2;
          ctx.lineCap = "round";
          ctx.lineJoin = "round";

          if (pts.length === 1) {
            const [px, py] = toPixel(pts[0]);
            ctx.beginPath();
            ctx.arc(px, py, radiusPx, 0, Math.PI * 2);
            ctx.fill();
          } else {
            ctx.beginPath();
            const [sx, sy] = toPixel(pts[0]);
            ctx.moveTo(sx, sy);
            for (let i = 1; i < pts.length; i++) {
              const [px, py] = toPixel(pts[i]);
              ctx.lineTo(px, py);
            }
            ctx.stroke();
            // Fill circles at each point for smooth coverage
            for (const pt of pts) {
              const [px, py] = toPixel(pt);
              ctx.beginPath();
              ctx.arc(px, py, radiusPx, 0, Math.PI * 2);
              ctx.fill();
            }
          }
        } else if (f.tool === "rectangle") {
          const corners = f.latlngs as any[];
          const [x1, y1] = toPixel(corners[0]);
          const [x2, y2] = toPixel(corners[1]);
          const rx = Math.min(x1, x2);
          const ry = Math.min(y1, y2);
          ctx.fillRect(rx, ry, Math.abs(x2 - x1), Math.abs(y2 - y1));
        } else if (f.tool === "polygon") {
          const pts = f.latlngs as any[];
          if (pts.length >= 3) {
            ctx.beginPath();
            const [sx, sy] = toPixel(pts[0]);
            ctx.moveTo(sx, sy);
            for (let i = 1; i < pts.length; i++) {
              const [px, py] = toPixel(pts[i]);
              ctx.lineTo(px, py);
            }
            ctx.closePath();
            ctx.fill();
          }
        }
      }

      // Export to base64
      const dataUrl = canvas.toDataURL("image/png");
      const base64 = dataUrl.split(",")[1];

      // Collect zone features (parking/speed_limit) and convert polygons to EPSG:25832
      const zones: any[] = [];
      for (const f of features) {
        if (f.occupancy !== "parking" && f.occupancy !== "speed_limit") continue;
        if (f.tool !== "polygon" && f.tool !== "rectangle") continue;
        let polyCoords: number[][] = [];
        if (f.tool === "polygon") {
          polyCoords = (f.latlngs as any[]).map((ll: any) => {
            const [x, y] = proj4("EPSG:4326", "EPSG:25832", [ll.lng, ll.lat]);
            return [x, y];
          });
        } else if (f.tool === "rectangle") {
          const c = f.latlngs as any[];
          const sw2 = c[0], ne2 = c[1];
          const corners = [
            [sw2.lng, sw2.lat], [ne2.lng, sw2.lat],
            [ne2.lng, ne2.lat], [sw2.lng, ne2.lat],
          ];
          polyCoords = corners.map(([lng, lat]) => {
            const [x, y] = proj4("EPSG:4326", "EPSG:25832", [lng, lat]);
            return [x, y];
          });
        }
        if (polyCoords.length < 3) continue;

        const zoneEntry: any = {
          name: f.zoneName || `Zone ${f.id}`,
          zoneType: f.occupancy,
          polygon: polyCoords,
        };
        if (f.occupancy === "parking") {
          if (f.goalPoint) {
            const [gpX, gpY] = proj4("EPSG:4326", "EPSG:25832", [f.goalPoint[1], f.goalPoint[0]]);
            zoneEntry.goalPoint = [gpX, gpY];
          }
          zoneEntry.isDefault = f.isDefault || false;
        }
        if (f.occupancy === "speed_limit") {
          zoneEntry.speedLimit = f.zoneSpeedLimit || 0.5;
        }
        zones.push(zoneEntry);
      }

      await fetchJSON("/api/mapgen/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: mapName,
          resolution: res,
          origin: [swX, swY, 0],
          imageData: base64,
          zones,
        }),
      });

      const zoneMsg = zones.length > 0 ? `, ${zones.length} zone(s)` : "";
      showToast(`Map "${mapName}" saved! (${widthPx}x${heightPx}px${zoneMsg})`, "success");

      // Clear session after successful save to prevent stale state
      try { sessionStorage.removeItem(SS_KEY); } catch {}
      setFeatures([]);
      setBbox(null);
      setMapName("");
    } catch (e: any) {
      showToast(e?.message || "Export failed", "error");
    } finally {
      setSaving(false);
    }
  };

  /* ── V2: Auto-fill from OSM ── */
  const autoFillOSM = async () => {
    if (!bbox) { showToast("Draw a bounding box first", "warning"); return; }
    setOsmLoading(true);
    try {
      const sw = bbox.getSouthWest();
      const ne = bbox.getNorthEast();
      const payload = {
        south: sw.lat, west: sw.lng,
        north: ne.lat, east: ne.lng,
      };
      console.log("[OSM Auto-fill] bbox payload:", JSON.stringify(payload));
      const data = await fetchJSON<any>("/api/mapgen/overpass", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const newFeatures: DrawnFeature[] = [];

      // First fill the whole bbox as "unknown" – roads and buildings will be drawn on top
      newFeatures.push({
        id: nextId(),
        tool: "rectangle",
        occupancy: "unknown",
        latlngs: [
          L.latLng(sw.lat, sw.lng),
          L.latLng(ne.lat, ne.lng),
        ],
      });

      // Draw classified features
      if (data.features) {
        for (const feat of data.features) {
          const geomType = feat.geometry?.type;
          const occ = feat.properties?.occupancy as OccupancyType || "occupied";

          if (geomType === "LineString" && feat.geometry.coordinates?.length >= 2) {
            // Roads: render as brush strokes with proper width
            const coords = feat.geometry.coordinates;
            const latlngs = coords.map((c: number[]) => L.latLng(c[1], c[0]));
            const width = feat.properties?.width || 4;
            newFeatures.push({
              id: nextId(),
              tool: "brush",
              occupancy: occ,
              latlngs,
              brushRadius: width / 2,
            });
          } else if (geomType === "Polygon" && feat.geometry.coordinates?.length > 0) {
            const ring = feat.geometry.coordinates[0];
            const latlngs = ring.map((c: number[]) => L.latLng(c[1], c[0]));
            if (latlngs.length >= 3) {
              newFeatures.push({
                id: nextId(),
                tool: "polygon",
                occupancy: occ,
                latlngs,
              });
            }
          }
        }
      }

      addFeatures((prev) => [...prev, ...newFeatures]);
      showToast(`Added ${newFeatures.length} features from OSM`, "success");
      showToast("Parking areas are shown as obstacles. Use the Parking Zone tool to mark areas where the robot can drive and park.", "info");

      // Start cooldown to avoid Overpass rate limiting (429)
      setOsmCooldown(30);
    } catch (e: any) {
      showToast(e?.message || "OSM auto-fill failed", "error");
    } finally {
      setOsmLoading(false);
    }
  };

  // Cooldown timer for Overpass rate limiting
  useEffect(() => {
    if (osmCooldown <= 0) return;
    const t = setTimeout(() => setOsmCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [osmCooldown]);

  /* ── Compute bbox info for display ── */
  const bboxInfo = bbox ? (() => {
    const sw = bbox.getSouthWest();
    const ne = bbox.getNorthEast();
    const [swX, swY] = proj4("EPSG:4326", "EPSG:25832", [sw.lng, sw.lat]);
    const [neX, neY] = proj4("EPSG:4326", "EPSG:25832", [ne.lng, ne.lat]);
    const w = Math.abs(neX - swX);
    const h = Math.abs(neY - swY);
    const res = parseFloat(resolution) || 0.1;
    return { w: w.toFixed(0), h: h.toFixed(0), px: Math.ceil(w / res), py: Math.ceil(h / res) };
  })() : null;

  /* ═══════════════════════════ RENDER ═══════════════════════════ */
  return (
    <div className="flex h-full overflow-hidden">
      {/* ── LEFT TOOLBAR ── */}
      <div className="w-56 shrink-0 border-r border-border bg-card p-3 space-y-4 overflow-y-auto">
        <h3 className="text-sm font-semibold text-foreground">Map Generator</h3>

        {/* Base layer */}
        <div className="space-y-1">
          <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">Base Layer</Label>
          <div className="flex gap-1">
            <Button size="sm" variant={baseLayer === "osm" ? "default" : "outline"} className="flex-1 text-xs h-7" onClick={() => setBaseLayer("osm")}>OSM</Button>
            <Button size="sm" variant={baseLayer === "ortho" ? "default" : "outline"} className="flex-1 text-xs h-7" onClick={() => setBaseLayer("ortho")}>Ortho</Button>
          </div>
        </div>

        {/* Tools */}
        <div className="space-y-1">
          <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">Tools</Label>
          {([
            { t: "pan" as ToolMode, icon: MousePointer, label: "Pan / Select" },
            { t: "bbox" as ToolMode, icon: Scan, label: "Bounding Box" },
            { t: "brush" as ToolMode, icon: Paintbrush, label: "Brush" },
            { t: "rectangle" as ToolMode, icon: Square, label: "Rectangle" },
            { t: "polygon" as ToolMode, icon: Pentagon, label: "Polygon" },
            { t: "eraser" as ToolMode, icon: Eraser, label: "Eraser" },
            { t: "edit" as ToolMode, icon: Pencil, label: "Edit Vertices" },
            { t: "pick" as ToolMode, icon: MousePointerClick, label: "Delete Object" },
          ]).map(({ t, icon: Icon, label }) => (
            <button
              key={t}
              onClick={() => { setTool(t); if (t !== "edit") setEditFeatureId(null); }}
              className={`w-full text-left px-2.5 py-1.5 rounded-md text-xs flex items-center gap-2 transition-colors ${
                tool === t
                  ? "bg-primary/15 text-primary font-medium"
                  : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
              }`}
            >
              <Icon className="h-3.5 w-3.5" /> {label}
            </button>
          ))}
        </div>

        {/* Brush size */}
        {(tool === "brush" || tool === "eraser") && (
          <div className="space-y-1">
            <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">
              {tool === "eraser" ? "Eraser" : "Brush"}: {brushSize}m
            </Label>
            <input
              type="range" min="1" max="50" value={brushSize}
              onChange={(e) => setBrushSize(parseInt(e.target.value))}
              className="w-full"
            />
          </div>
        )}

        {/* Occupancy type */}
        <div className="space-y-1">
          <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">Draw Type</Label>
          {([
            { o: "free" as OccupancyType, label: "Free (white)", color: "#fff", icon: null },
            { o: "occupied" as OccupancyType, label: "Occupied (black)", color: "#000", icon: null },
            { o: "unknown" as OccupancyType, label: "Unknown (grey)", color: "#ccc", icon: null },
            { o: "parking" as OccupancyType, label: "Parking zone", color: "#3b82f6", icon: ParkingSquare },
            { o: "speed_limit" as OccupancyType, label: "Speed limit zone", color: "#f59e0b", icon: Gauge },
          ]).map(({ o, label, color, icon: Icon }) => (
            <button
              key={o}
              onClick={() => setOccupancy(o)}
              className={`w-full text-left px-2.5 py-1.5 rounded-md text-xs flex items-center gap-2 transition-colors ${
                occupancy === o
                  ? "bg-primary/15 text-primary font-medium"
                  : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
              }`}
            >
              <div className="w-3.5 h-3.5 rounded border border-border shrink-0" style={{ backgroundColor: color }} />
              {Icon && <Icon className="h-3 w-3" />}
              {label}
            </button>
          ))}
        </div>

        {/* Zone features list */}
        {(() => {
          const zoneFeatures = features.filter((f) => f.occupancy === "parking" || f.occupancy === "speed_limit");
          if (zoneFeatures.length === 0) return null;
          return (
            <div className="space-y-1.5 border-t border-border pt-3">
              <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">Zone Metadata</Label>
              <div className="space-y-2 max-h-52 overflow-y-auto">
                {zoneFeatures.map((zf) => (
                  <div
                    key={zf.id}
                    className={`rounded-md border p-2 space-y-1.5 text-xs ${
                      selectedFeatureId === zf.id ? "border-primary bg-primary/5" : "border-border bg-secondary/20"
                    }`}
                    onClick={() => setSelectedFeatureId(zf.id)}
                  >
                    <div className="flex items-center gap-1">
                      <div className="w-2.5 h-2.5 rounded" style={{ backgroundColor: zf.occupancy === "parking" ? "#3b82f6" : "#f59e0b" }} />
                      <span className="text-muted-foreground">{zf.occupancy === "parking" ? "P" : "S"}</span>
                    </div>
                    <Input
                      placeholder="Zone name"
                      value={zf.zoneName || ""}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => {
                        const val = e.target.value;
                        setFeatures((prev) => prev.map((f) => f.id === zf.id ? { ...f, zoneName: val } : f));
                      }}
                      className="h-6 text-xs"
                    />
                    {zf.occupancy === "parking" && (
                      <>
                        <label className="flex items-center gap-1.5 text-[10px] text-muted-foreground cursor-pointer">
                          <input
                            type="checkbox"
                            checked={zf.isDefault || false}
                            onChange={(e) => {
                              const checked = e.target.checked;
                              setFeatures((prev) => prev.map((f) => {
                                if (f.id === zf.id) return { ...f, isDefault: checked };
                                // Only one default
                                if (checked && f.occupancy === "parking") return { ...f, isDefault: false };
                                return f;
                              }));
                            }}
                          />
                          Default parking
                        </label>
                        <Button
                          size="sm"
                          variant={settingGoalPoint && selectedFeatureId === zf.id ? "default" : "outline"}
                          className="w-full text-[10px] h-6"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (settingGoalPoint && selectedFeatureId === zf.id) {
                              setSettingGoalPoint(false);
                            } else {
                              setSelectedFeatureId(zf.id);
                              setSettingGoalPoint(true);
                            }
                          }}
                        >
                          <MapPin className="h-3 w-3 mr-1" />
                          {settingGoalPoint && selectedFeatureId === zf.id
                            ? "Cancel"
                            : zf.goalPoint ? "Move goal point" : "Set goal point"}
                        </Button>
                        {zf.goalPoint && (
                          <p className="text-[9px] text-green-500">Goal: {(() => { const [x, y] = proj4("EPSG:4326", "EPSG:25832", [zf.goalPoint[1], zf.goalPoint[0]]); return `${x.toFixed(1)}, ${y.toFixed(1)}`; })()}</p>
                        )}
                      </>
                    )}
                    {zf.occupancy === "speed_limit" && (
                      <div className="flex items-center gap-1">
                        <span className="text-[10px] text-muted-foreground shrink-0">Speed:</span>
                        <Input
                          type="number"
                          step="0.1"
                          placeholder="0.5"
                          value={zf.zoneSpeedLimit ?? ""}
                          onClick={(e) => e.stopPropagation()}
                          onChange={(e) => {
                            const val = parseFloat(e.target.value) || undefined;
                            setFeatures((prev) => prev.map((f) => f.id === zf.id ? { ...f, zoneSpeedLimit: val } : f));
                          }}
                          className="h-6 text-xs flex-1"
                        />
                        <span className="text-[10px] text-muted-foreground">m/s</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          );
        })()}

        {settingGoalPoint && (
          <div className="bg-green-500/10 border border-green-500/30 rounded-md p-2 text-xs text-green-400 flex items-center justify-between">
            <span>Click on the map to set goal point</span>
            <button onClick={() => setSettingGoalPoint(false)} className="text-green-300 hover:text-white ml-2 font-bold">✕</button>
          </div>
        )}

        {/* Undo / Redo / Clear */}
        <div className="flex gap-1">
          <Button size="sm" variant="outline" className="flex-1 text-xs h-7" onClick={undo} disabled={undoStack.length === 0 && polyVertexCount === 0}>
            <Undo2 className="h-3 w-3 mr-1" /> Undo
          </Button>
          <Button size="sm" variant="outline" className="flex-1 text-xs h-7" onClick={redo} disabled={redoStack.length === 0}>
            <Redo2 className="h-3 w-3 mr-1" /> Redo
          </Button>
        </div>
        <Button size="sm" variant="outline" className="w-full text-xs h-7 text-red-400" onClick={clearAll} disabled={features.length === 0 && polyVertexCount === 0}>
          <Trash2 className="h-3 w-3 mr-1" /> Clear All
        </Button>

        <p className="text-[10px] text-muted-foreground">
          {features.length} object{features.length !== 1 ? "s" : ""}
          {polyVertexCount > 0 && ` | ${polyVertexCount} vertices`}
        </p>
      </div>

      {/* ── CENTER: MAP ── */}
      <div className="flex-1 relative">
        {/* Search bar - centered */}
        <div className="absolute top-3 left-0 right-0 z-[1000] flex justify-center pointer-events-none">
          <div className="relative max-w-md w-full mx-4 pointer-events-auto">
            <Search className="absolute left-2.5 top-2 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search street, e.g. Sonnenstraße, Dortmund"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 rounded-lg border border-border bg-card/90 backdrop-blur text-sm text-foreground shadow-md focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
            {searchResults.length > 0 && (
              <div className="absolute top-full mt-1 w-full bg-card border border-border rounded-lg shadow-lg max-h-48 overflow-y-auto z-[1001]">
                {searchResults.map((r: any, i: number) => (
                  <button
                    key={i}
                    className="w-full text-left px-3 py-2 text-xs text-foreground hover:bg-secondary/50 border-b border-border last:border-0"
                    onClick={() => panToResult(r)}
                  >
                    <MapPin className="h-3 w-3 inline mr-1 text-muted-foreground" />
                    {r.display_name}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Eye toggle to hide/show drawn features */}
        <button
          onClick={() => setCanvasVisible((v) => !v)}
          className="absolute bottom-3 right-3 z-[1000] p-1.5 rounded-md bg-card/90 border border-border hover:bg-accent transition-colors shadow-md"
          title={canvasVisible ? "Hide drawn features" : "Show drawn features"}
        >
          {canvasVisible ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
        </button>

        {/* Leaflet map (canvas overlay is created inside programmatically) */}
        <div ref={mapDivRef} className="absolute inset-0 z-0" />
      </div>

      {/* ── RIGHT PANEL: EXPORT ── */}
      <div className="w-56 shrink-0 border-l border-border bg-card p-3 space-y-4 overflow-y-auto">
        <h3 className="text-sm font-semibold text-foreground">Export Settings</h3>

        {/* Bbox info */}
        {bboxInfo ? (
          <div className="bg-secondary/30 rounded-lg p-2 text-xs space-y-0.5">
            <div className="flex items-center justify-between">
              <p className="text-muted-foreground">Bounding Box:</p>
              <button onClick={() => setBbox(null)} className="text-red-400 hover:text-red-300 text-[10px]">✕ Remove</button>
            </div>
            <p className="text-foreground">{bboxInfo.w} x {bboxInfo.h} m</p>
            <p className="text-foreground">{bboxInfo.px} x {bboxInfo.py} px</p>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            Use the <strong>Bounding Box</strong> tool to select the export area.
          </p>
        )}

        <div className="space-y-1">
          <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">Map Name</Label>
          <Input value={mapName} onChange={(e) => setMapName(e.target.value)} className="h-8 text-sm" placeholder="My Map" />
        </div>

        <div className="space-y-1">
          <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">Resolution (m/px)</Label>
          <Input type="number" step="0.01" value={resolution} onChange={(e) => setResolution(e.target.value)} className="h-8 text-sm" />
        </div>

        <Button className="w-full gap-2" onClick={exportMap} disabled={saving || !bbox}>
          <Save className="h-4 w-4" /> {saving ? "Saving..." : "Save Map"}
        </Button>

        <hr className="border-border" />

        {/* V2: OSM Auto-fill */}
        <h3 className="text-sm font-semibold text-foreground">Auto-Fill (OSM)</h3>
        <p className="text-[10px] text-muted-foreground">
          Fetches buildings, roads, water from OpenStreetMap and auto-classifies as occupancy grid. Draw a bounding box first.
        </p>
        <Button
          className="w-full gap-2"
          variant="outline"
          onClick={autoFillOSM}
          disabled={osmLoading || !bbox || osmCooldown > 0}
        >
          <Wand2 className="h-4 w-4" /> {osmLoading ? "Loading OSM..." : osmCooldown > 0 ? `Wait ${osmCooldown}s` : "Auto-Fill from OSM"}
        </Button>
      </div>
    </div>
  );
}
