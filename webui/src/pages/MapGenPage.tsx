import { useRef, useState, useEffect, useCallback } from "react";
import { fetchJSON } from "@/utils/api";
import { showToast } from "@/lib/toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Paintbrush, Eraser, Square, Circle, Save, RotateCcw } from "lucide-react";

type Tool = "free" | "occupied" | "unknown" | "eraser";
type BrushShape = "circle" | "square";

const TOOL_COLORS: Record<Tool, string> = {
  free: "#FFFFFF",
  occupied: "#000000",
  unknown: "#CDCDCD",
  eraser: "#CDCDCD",
};

const TOOL_LABELS: Record<Tool, string> = {
  free: "Free (white)",
  occupied: "Occupied (black)",
  unknown: "Unknown (grey)",
  eraser: "Eraser",
};

export default function MapGenPage() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [tool, setTool] = useState<Tool>("free");
  const [brushSize, setBrushSize] = useState(10);
  const [brushShape, setBrushShape] = useState<BrushShape>("circle");
  const [resolution, setResolution] = useState("0.05");
  const [originX, setOriginX] = useState("0");
  const [originY, setOriginY] = useState("0");
  const [mapName, setMapName] = useState("");
  const [canvasSize] = useState({ w: 800, h: 600 });
  const [isDrawing, setIsDrawing] = useState(false);
  const [saving, setSaving] = useState(false);

  // Initialize canvas with unknown (grey)
  useEffect(() => {
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#CDCDCD";
    ctx.fillRect(0, 0, canvasSize.w, canvasSize.h);
  }, [canvasSize]);

  const draw = useCallback(
    (x: number, y: number) => {
      const ctx = canvasRef.current?.getContext("2d");
      if (!ctx) return;
      ctx.fillStyle = TOOL_COLORS[tool];
      if (brushShape === "circle") {
        ctx.beginPath();
        ctx.arc(x, y, brushSize / 2, 0, Math.PI * 2);
        ctx.fill();
      } else {
        const half = brushSize / 2;
        ctx.fillRect(x - half, y - half, brushSize, brushSize);
      }
    },
    [tool, brushSize, brushShape]
  );

  const getPos = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const scaleX = canvasSize.w / rect.width;
    const scaleY = canvasSize.h / rect.height;
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
    };
  };

  const onMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    setIsDrawing(true);
    const { x, y } = getPos(e);
    draw(x, y);
  };

  const onMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDrawing) return;
    const { x, y } = getPos(e);
    draw(x, y);
  };

  const onMouseUp = () => setIsDrawing(false);

  const clearCanvas = () => {
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#CDCDCD";
    ctx.fillRect(0, 0, canvasSize.w, canvasSize.h);
  };

  const onSave = async () => {
    if (!mapName.trim()) {
      showToast("Map name is required", "warning");
      return;
    }
    setSaving(true);
    try {
      const dataUrl = canvasRef.current!.toDataURL("image/png");
      const base64 = dataUrl.split(",")[1];
      const res = await fetchJSON<any>("/api/mapgen/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: mapName,
          resolution: parseFloat(resolution) || 0.05,
          origin: [parseFloat(originX) || 0, parseFloat(originY) || 0, 0],
          imageData: base64,
        }),
      });
      showToast(`Map "${mapName}" generated! ID: ${res.mapId}`, "success");
    } catch (e: any) {
      showToast(e?.message || "Failed to generate map", "error");
    } finally {
      setSaving(false);
    }
  };

  // Generate YAML preview
  const yamlPreview = `image: map.png
resolution: ${resolution}
origin: [${originX}, ${originY}, 0.0]
negate: 0
occupied_thresh: 0.65
free_thresh: 0.196`;

  return (
    <div className="flex flex-col lg:flex-row h-full overflow-auto">
      {/* Canvas area */}
      <div className="flex-1 p-4 flex flex-col items-center">
        <h2 className="text-lg font-semibold text-foreground mb-3">Map Generator</h2>
        <div className="border border-border rounded-lg overflow-hidden bg-card" style={{ maxWidth: "100%" }}>
          <canvas
            ref={canvasRef}
            width={canvasSize.w}
            height={canvasSize.h}
            className="cursor-crosshair block max-w-full h-auto"
            onMouseDown={onMouseDown}
            onMouseMove={onMouseMove}
            onMouseUp={onMouseUp}
            onMouseLeave={onMouseUp}
          />
        </div>
        {/* YAML Preview */}
        <div className="mt-4 w-full max-w-2xl">
          <p className="text-xs text-muted-foreground mb-1">Generated YAML Preview:</p>
          <pre className="bg-secondary/30 rounded-lg p-3 text-xs text-muted-foreground font-mono whitespace-pre">
            {yamlPreview}
          </pre>
        </div>
      </div>

      {/* Toolbox sidebar */}
      <div className="w-full lg:w-64 border-t lg:border-t-0 lg:border-l border-border p-4 space-y-4 bg-card">
        <h3 className="text-sm font-semibold text-foreground">Drawing Tools</h3>

        {/* Tool selection */}
        <div className="space-y-1">
          {(["free", "occupied", "unknown", "eraser"] as Tool[]).map((t) => (
            <button
              key={t}
              onClick={() => setTool(t)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm flex items-center gap-2 transition-colors ${
                tool === t
                  ? "bg-primary/15 text-primary font-medium"
                  : "text-muted-foreground hover:bg-secondary/50"
              }`}
            >
              <div
                className="w-4 h-4 rounded border border-border"
                style={{ backgroundColor: TOOL_COLORS[t] }}
              />
              {TOOL_LABELS[t]}
            </button>
          ))}
        </div>

        {/* Brush settings */}
        <div className="space-y-2">
          <Label className="text-xs text-muted-foreground">Brush Size: {brushSize}px</Label>
          <input
            type="range"
            min="1"
            max="50"
            value={brushSize}
            onChange={(e) => setBrushSize(parseInt(e.target.value))}
            className="w-full"
          />
        </div>

        <div className="flex gap-1">
          <Button
            size="sm"
            variant={brushShape === "circle" ? "default" : "outline"}
            className="flex-1"
            onClick={() => setBrushShape("circle")}
          >
            <Circle className="h-3 w-3" />
          </Button>
          <Button
            size="sm"
            variant={brushShape === "square" ? "default" : "outline"}
            className="flex-1"
            onClick={() => setBrushShape("square")}
          >
            <Square className="h-3 w-3" />
          </Button>
        </div>

        <Button variant="outline" size="sm" className="w-full" onClick={clearCanvas}>
          <RotateCcw className="h-3 w-3 mr-1" /> Clear
        </Button>

        <hr className="border-border" />

        {/* Map settings */}
        <div className="space-y-2">
          <Label className="text-xs text-muted-foreground">Resolution (m/px)</Label>
          <Input
            type="number"
            step="0.01"
            value={resolution}
            onChange={(e) => setResolution(e.target.value)}
            className="h-8 text-sm"
          />
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Origin X</Label>
            <Input
              type="number"
              value={originX}
              onChange={(e) => setOriginX(e.target.value)}
              className="h-8 text-sm"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Origin Y</Label>
            <Input
              type="number"
              value={originY}
              onChange={(e) => setOriginY(e.target.value)}
              className="h-8 text-sm"
            />
          </div>
        </div>

        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">Map Name</Label>
          <Input
            value={mapName}
            onChange={(e) => setMapName(e.target.value)}
            className="h-8 text-sm"
            placeholder="My Map"
          />
        </div>

        <Button className="w-full gap-2" onClick={onSave} disabled={saving}>
          <Save className="h-4 w-4" /> {saving ? "Saving..." : "Save Map"}
        </Button>
      </div>
    </div>
  );
}
