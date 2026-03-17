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
  MousePointer, Undo2, Layers, MapPin, Gauge, ParkingSquare,
  Wand2, Trash2,
} from "lucide-react";

/* ── proj4 + CRS ── */
proj4.defs(
  "EPSG:25832",
  "+proj=utm +zone=32 +ellps=GRS80 +units=m +no_defs +type=crs"
);

/* ── Types ── */
type ToolMode = "pan" | "brush" | "rectangle" | "polygon" | "eraser" | "bbox";
type OccupancyType = "free" | "occupied" | "unknown" | "parking" | "speed_limit";

interface DrawnFeature {
  id: string;
  tool: "brush" | "rectangle" | "polygon";
  occupancy: OccupancyType;
  latlngs: any[] | any[][]; // L.LatLng arrays
  brushRadius?: number; // meters, for brush strokes
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

/* ═══════════════════════════ COMPONENT ═══════════════════════════ */

export default function MapGenPage() {
  /* ── Refs ── */
  const mapDivRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const featuresLayerRef = useRef<any>(null);
  const bboxRectRef = useRef<any>(null);
  const tempLayerRef = useRef<any>(null);

  /* ── State ── */
  const [tool, setTool] = useState<ToolMode>("pan");
  const [occupancy, setOccupancy] = useState<OccupancyType>("occupied");
  const [brushSize, setBrushSize] = useState(3); // meters
  const [features, setFeatures] = useState<DrawnFeature[]>([]);
  const [bbox, setBbox] = useState<any>(null);
  const [mapName, setMapName] = useState("");
  const [resolution, setResolution] = useState("0.05");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);
  const [osmLoading, setOsmLoading] = useState(false);
  const [baseLayer, setBaseLayer] = useState<"osm" | "ortho">("osm");

  // Drawing state (not in React state for performance)
  const drawingRef = useRef(false);
  const currentStrokeRef = useRef<any[]>([]);
  const polyVerticesRef = useRef<any[]>([]);

  /* ── Initialize Leaflet ── */
  useEffect(() => {
    if (!mapDivRef.current || mapRef.current) return;

    const map = L.map(mapDivRef.current, {
      center: NRW_CENTER,
      zoom: NRW_ZOOM,
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

    const fg = L.layerGroup().addTo(map);
    featuresLayerRef.current = fg;
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      featuresLayerRef.current = null;
    };
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

  /* ── Re-render features on Leaflet ── */
  useEffect(() => {
    const fg = featuresLayerRef.current;
    if (!fg) return;
    fg.clearLayers();

    for (const f of features) {
      const style = {
        color: OCCUPANCY_COLORS[f.occupancy].stroke,
        fillColor: OCCUPANCY_COLORS[f.occupancy].fill,
        fillOpacity: 0.6,
        weight: 2,
      };

      if (f.tool === "brush" && f.latlngs.length > 0) {
        const coords = f.latlngs as any[];
        if (coords.length === 1) {
          L.circle(coords[0], { ...style, radius: f.brushRadius || brushSize }).addTo(fg);
        } else {
          const poly = L.polyline(coords, { ...style, weight: (f.brushRadius || brushSize) * 2 / getMetersPerPixel() });
          poly.addTo(fg);
          // Add circles at endpoints for rounded look
          L.circle(coords[0], { ...style, radius: f.brushRadius || brushSize }).addTo(fg);
          L.circle(coords[coords.length - 1], { ...style, radius: f.brushRadius || brushSize }).addTo(fg);
        }
      } else if (f.tool === "rectangle" && f.latlngs.length >= 2) {
        const corners = f.latlngs as any[];
        const bounds = L.latLngBounds(corners[0], corners[1]);
        L.rectangle(bounds, style).addTo(fg);
      } else if (f.tool === "polygon" && (f.latlngs as any[]).length >= 3) {
        L.polygon(f.latlngs as any[], style).addTo(fg);
      }
    }
  }, [features, brushSize]);

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

  /* ── Helper: meters per pixel at current zoom ── */
  function getMetersPerPixel() {
    const map = mapRef.current;
    if (!map) return 1;
    const center = map.getCenter();
    const zoom = map.getZoom();
    return 40075016.686 * Math.cos((center.lat * Math.PI) / 180) / Math.pow(2, zoom + 8);
  }

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
      bbox: "crosshair",
    };
    el.style.cursor = cursors[tool] || "default";
  }, [tool]);

  /* ── Disable map drag when drawing ── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (tool === "pan") {
      map.dragging.enable();
      map.doubleClickZoom.enable();
    } else {
      map.dragging.disable();
      map.doubleClickZoom.disable();
    }
  }, [tool]);

  /* ── Map mouse events for drawing ── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    function onMouseDown(e: any) {
      if (tool === "pan") return;

      if (tool === "brush" || tool === "eraser") {
        drawingRef.current = true;
        currentStrokeRef.current = [e.latlng];
      } else if (tool === "rectangle" || tool === "bbox") {
        drawingRef.current = true;
        currentStrokeRef.current = [e.latlng];
      }
      // Polygon uses click, not mousedown
    }

    function onMouseMove(e: any) {
      if (!drawingRef.current) return;

      if (tool === "brush" || tool === "eraser") {
        currentStrokeRef.current.push(e.latlng);
        // Show preview
        if (tempLayerRef.current) map.removeLayer(tempLayerRef.current);
        const occ = tool === "eraser" ? "unknown" : occupancy;
        tempLayerRef.current = L.polyline(currentStrokeRef.current, {
          color: OCCUPANCY_COLORS[occ].stroke,
          weight: brushSize * 2 / getMetersPerPixel(),
          opacity: 0.5,
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
      if (!drawingRef.current) return;
      drawingRef.current = false;
      if (tempLayerRef.current) {
        map.removeLayer(tempLayerRef.current);
        tempLayerRef.current = null;
      }

      if (tool === "brush" || tool === "eraser") {
        const pts = currentStrokeRef.current;
        if (pts.length > 0) {
          const occ = tool === "eraser" ? "unknown" : occupancy;
          setFeatures((prev) => [
            ...prev,
            { id: nextId(), tool: "brush", occupancy: occ, latlngs: [...pts], brushRadius: brushSize },
          ]);
        }
        currentStrokeRef.current = [];
      } else if (tool === "rectangle") {
        const start = currentStrokeRef.current[0];
        if (start) {
          setFeatures((prev) => [
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
      if (tool === "polygon") {
        polyVerticesRef.current.push(e.latlng);
        // Preview
        if (tempLayerRef.current) map.removeLayer(tempLayerRef.current);
        if (polyVerticesRef.current.length >= 2) {
          tempLayerRef.current = L.polyline(polyVerticesRef.current, {
            color: OCCUPANCY_COLORS[occupancy].stroke,
            weight: 2,
          }).addTo(map);
        }
      }
    }

    function onDblClick(e: any) {
      if (tool === "polygon" && polyVerticesRef.current.length >= 3) {
        setFeatures((prev) => [
          ...prev,
          { id: nextId(), tool: "polygon", occupancy, latlngs: [...polyVerticesRef.current] },
        ]);
        polyVerticesRef.current = [];
        if (tempLayerRef.current) {
          map.removeLayer(tempLayerRef.current);
          tempLayerRef.current = null;
        }
      }
    }

    map.on("mousedown", onMouseDown);
    map.on("mousemove", onMouseMove);
    map.on("mouseup", onMouseUp);
    map.on("click", onClick);
    map.on("dblclick", onDblClick);

    return () => {
      map.off("mousedown", onMouseDown);
      map.off("mousemove", onMouseMove);
      map.off("mouseup", onMouseUp);
      map.off("click", onClick);
      map.off("dblclick", onDblClick);
    };
  }, [tool, occupancy, brushSize]);

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

  /* ── Undo ── */
  const undo = () => setFeatures((prev) => prev.slice(0, -1));

  /* ── Clear all ── */
  const clearAll = () => { setFeatures([]); };

  /* ── Export: rasterize to PNG and save ── */
  const exportMap = async () => {
    if (!bbox) { showToast("Draw a bounding box first", "warning"); return; }
    if (!mapName.trim()) { showToast("Enter a map name", "warning"); return; }

    setSaving(true);
    try {
      const res = parseFloat(resolution) || 0.05;

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

        if (f.tool === "brush") {
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

      await fetchJSON("/api/mapgen/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: mapName,
          resolution: res,
          origin: [swX, swY, 0],
          imageData: base64,
        }),
      });

      showToast(`Map "${mapName}" saved! (${widthPx}x${heightPx}px)`, "success");
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
      const data = await fetchJSON<any>("/api/mapgen/overpass", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          south: sw.lat, west: sw.lng,
          north: ne.lat, east: ne.lng,
        }),
      });

      const newFeatures: DrawnFeature[] = [];

      // First fill the whole bbox as "free" (roads/walkable)
      newFeatures.push({
        id: nextId(),
        tool: "rectangle",
        occupancy: "free",
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

          if (geomType === "Polygon" && feat.geometry.coordinates?.length > 0) {
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

      setFeatures((prev) => [...prev, ...newFeatures]);
      showToast(`Added ${newFeatures.length} features from OSM`, "success");
    } catch (e: any) {
      showToast(e?.message || "OSM auto-fill failed", "error");
    } finally {
      setOsmLoading(false);
    }
  };

  /* ── Compute bbox info for display ── */
  const bboxInfo = bbox ? (() => {
    const sw = bbox.getSouthWest();
    const ne = bbox.getNorthEast();
    const [swX, swY] = proj4("EPSG:4326", "EPSG:25832", [sw.lng, sw.lat]);
    const [neX, neY] = proj4("EPSG:4326", "EPSG:25832", [ne.lng, ne.lat]);
    const w = Math.abs(neX - swX);
    const h = Math.abs(neY - swY);
    const res = parseFloat(resolution) || 0.05;
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
            { t: "polygon" as ToolMode, icon: Pentagon, label: "Polygon (dbl-click)" },
            { t: "eraser" as ToolMode, icon: Eraser, label: "Eraser (→ unknown)" },
          ]).map(({ t, icon: Icon, label }) => (
            <button
              key={t}
              onClick={() => setTool(t)}
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
              Brush: {brushSize}m
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

        {/* Undo / Clear */}
        <div className="flex gap-1">
          <Button size="sm" variant="outline" className="flex-1 text-xs h-7" onClick={undo} disabled={features.length === 0}>
            <Undo2 className="h-3 w-3 mr-1" /> Undo
          </Button>
          <Button size="sm" variant="outline" className="flex-1 text-xs h-7 text-red-400" onClick={clearAll} disabled={features.length === 0}>
            <Trash2 className="h-3 w-3 mr-1" /> Clear
          </Button>
        </div>

        <p className="text-[10px] text-muted-foreground">
          {features.length} feature{features.length !== 1 ? "s" : ""} drawn
        </p>
      </div>

      {/* ── CENTER: MAP ── */}
      <div className="flex-1 relative">
        {/* Search bar */}
        <div className="absolute top-3 left-3 right-56 z-[1000]">
          <div className="relative max-w-md">
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

        {/* Leaflet map */}
        <div ref={mapDivRef} className="absolute inset-0 z-0" />
      </div>

      {/* ── RIGHT PANEL: EXPORT ── */}
      <div className="w-56 shrink-0 border-l border-border bg-card p-3 space-y-4 overflow-y-auto">
        <h3 className="text-sm font-semibold text-foreground">Export Settings</h3>

        {/* Bbox info */}
        {bboxInfo ? (
          <div className="bg-secondary/30 rounded-lg p-2 text-xs space-y-0.5">
            <p className="text-muted-foreground">Bounding Box:</p>
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
          disabled={osmLoading || !bbox}
        >
          <Wand2 className="h-4 w-4" /> {osmLoading ? "Loading OSM..." : "Auto-Fill from OSM"}
        </Button>
      </div>
    </div>
  );
}
