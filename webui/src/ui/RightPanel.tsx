import { useState } from "react";
import { useSelectionStore, Zone } from "../utils/state";
import { sendMissionInstant, sendMissionScheduled, createZone, deleteZone, fetchZones } from "../utils/api";
import { showToast } from "@/lib/toast";
import { useAuthStore } from "@/utils/auth";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Send, Layers, Trash2, Eye, EyeOff } from "lucide-react";

export default function RightPanel() {
  const robotId = useSelectionStore((s) => s.selectedRobotId);
  const mapId = useSelectionStore((s) => s.selectedMapId);
  const destX = useSelectionStore((s) => s.destX);
  const destY = useSelectionStore((s) => s.destY);
  const zones = useSelectionStore((s) => s.zones);
  const showZones = useSelectionStore((s) => s.showZones);
  const userRole = useAuthStore((s) => s.user?.role);
  const canEdit = userRole === "admin" || userRole === "operator";
  const [scheduledTime, setScheduledTime] = useState("");
  const [cron, setCron] = useState("");

  // Zone form
  const [zoneName, setZoneName] = useState("");
  const [zoneType, setZoneType] = useState<"parking" | "speed_limit">("parking");
  const [zoneSpeed, setZoneSpeed] = useState("");
  const [zoneVerts, setZoneVerts] = useState("");

  const onCreateZone = async () => {
    if (!mapId) { showToast("Select a map first", "warning"); return; }
    if (!zoneName.trim()) { showToast("Zone name required", "warning"); return; }
    try {
      const polygon = JSON.parse(zoneVerts);
      if (!Array.isArray(polygon) || polygon.length < 3) {
        showToast("Enter at least 3 vertices as JSON [[x,y],...]", "warning");
        return;
      }
      await createZone(mapId, {
        name: zoneName,
        zoneType,
        polygon,
        speedLimit: zoneType === "speed_limit" ? parseFloat(zoneSpeed) || undefined : undefined,
      });
      showToast("Zone created", "success");
      setZoneName("");
      setZoneVerts("");
      setZoneSpeed("");
      // Refresh zones
      const z = await fetchZones(mapId);
      useSelectionStore.getState().setZones(z || []);
    } catch (e: any) {
      showToast(e?.message || "Failed to create zone", "error");
    }
  };

  const onDeleteZone = async (zoneId: string) => {
    if (!mapId) return;
    try {
      await deleteZone(mapId, zoneId);
      showToast("Zone deleted", "success");
      const z = await fetchZones(mapId);
      useSelectionStore.getState().setZones(z || []);
    } catch (e: any) {
      showToast(e?.message || "Failed to delete zone", "error");
    }
  };

  const ready = Boolean(robotId && mapId && destX != null && destY != null);

  const onSendInstant = async () => {
    if (!ready) {
      showToast("Select robot, map, and a valid destination", "warning");
      return;
    }
    try {
      await sendMissionInstant({
        robotId: robotId!,
        mapId: mapId!,
        x: destX!,
        y: destY!,
      });
      showToast("Mission sent", "success");
    } catch (e: any) {
      showToast(e?.message || "Send failed", "error");
    }
  };

  const onSendScheduled = async () => {
    if (!ready) {
      showToast("Select robot, map, and a valid destination", "warning");
      return;
    }
    if (!scheduledTime && !cron) {
      showToast("Provide scheduled time or cron", "warning");
      return;
    }
    try {
      await sendMissionScheduled({
        robotId: robotId!,
        mapId: mapId!,
        x: destX!,
        y: destY!,
        scheduledTime: scheduledTime || undefined,
        cron: cron || undefined,
      });
      showToast("Scheduled mission created", "success");
    } catch (e: any) {
      showToast(e?.message || "Schedule failed", "error");
    }
  };

  const coordFields = (
    <div className="grid grid-cols-2 md:grid-cols-1 gap-2">
      <div className="space-y-1">
        <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">
          X (EPSG:25832)
        </Label>
        <Input
          readOnly
          value={destX ?? ""}
          className="font-mono text-sm bg-secondary/30 h-8"
        />
      </div>
      <div className="space-y-1">
        <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">
          Y (EPSG:25832)
        </Label>
        <Input
          readOnly
          value={destY ?? ""}
          className="font-mono text-sm bg-secondary/30 h-8"
        />
      </div>
    </div>
  );

  return (
    <div className="p-3">
      <Tabs defaultValue="regular">
        <TabsList className="w-full bg-secondary/50">
          <TabsTrigger value="regular" className="flex-1 text-xs">
            Regular
          </TabsTrigger>
          <TabsTrigger value="scheduled" className="flex-1 text-xs">
            Scheduled
          </TabsTrigger>
          <TabsTrigger value="cron" className="flex-1 text-xs">
            CRON
          </TabsTrigger>
          <TabsTrigger value="zones" className="flex-1 text-xs">
            Zones
          </TabsTrigger>
        </TabsList>

        <TabsContent value="regular" className="mt-3 space-y-3">
          {coordFields}
          <Button
            className="w-full gap-2"
            disabled={!ready}
            onClick={onSendInstant}
          >
            <Send className="h-4 w-4" />
            Send Mission
          </Button>
        </TabsContent>

        <TabsContent value="scheduled" className="mt-3 space-y-3">
          {coordFields}
          <div className="space-y-1">
            <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">
              Scheduled Time
            </Label>
            <Input
              type="datetime-local"
              value={scheduledTime}
              onChange={(e) => setScheduledTime(e.target.value)}
              className="h-8 text-sm"
            />
          </div>
          <Button
            className="w-full gap-2"
            disabled={!ready}
            onClick={onSendScheduled}
          >
            <Send className="h-4 w-4" />
            Send Mission
          </Button>
        </TabsContent>

        <TabsContent value="cron" className="mt-3 space-y-3">
          {coordFields}
          <div className="space-y-1">
            <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">
              CRON (m h dom mon dow)
            </Label>
            <Input
              placeholder="0 9 * * *"
              value={cron}
              onChange={(e) => setCron(e.target.value)}
              className="h-8 text-sm font-mono"
            />
          </div>
          <Button
            className="w-full gap-2"
            disabled={!ready}
            onClick={onSendScheduled}
          >
            <Send className="h-4 w-4" />
            Send Mission
          </Button>
        </TabsContent>

        <TabsContent value="zones" className="mt-3 space-y-3">
          {/* Toggle zones visibility */}
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Show Zones</span>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => useSelectionStore.getState().setShowZones(!showZones)}
            >
              {showZones ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
            </Button>
          </div>

          {/* Zone list */}
          {zones.length > 0 && (
            <div className="space-y-1.5 max-h-40 overflow-y-auto">
              {zones.map((z: Zone) => (
                <div key={z.zoneId} className="flex items-center justify-between bg-secondary/30 rounded-md px-2 py-1.5 text-xs">
                  <div>
                    <span className={z.zoneType === "parking" ? "text-blue-400" : "text-amber-400"}>
                      {z.zoneType === "parking" ? "P" : "S"}
                    </span>{" "}
                    <span className="text-foreground">{z.name}</span>
                    {z.speedLimit ? <span className="text-muted-foreground ml-1">({z.speedLimit} m/s)</span> : null}
                  </div>
                  {canEdit && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 text-red-400 hover:text-red-300"
                      onClick={() => onDeleteZone(z.zoneId)}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Create zone form */}
          {canEdit && (
            <div className="space-y-2 border-t border-border pt-3">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider">New Zone</p>
              <Input
                placeholder="Zone name"
                value={zoneName}
                onChange={(e) => setZoneName(e.target.value)}
                className="h-8 text-sm"
              />
              <select
                value={zoneType}
                onChange={(e) => setZoneType(e.target.value as any)}
                className="w-full h-8 rounded-md border border-border bg-background text-sm px-2 text-foreground"
              >
                <option value="parking">Parking</option>
                <option value="speed_limit">Speed Limit</option>
              </select>
              {zoneType === "speed_limit" && (
                <Input
                  type="number"
                  step="0.1"
                  placeholder="Speed limit (m/s)"
                  value={zoneSpeed}
                  onChange={(e) => setZoneSpeed(e.target.value)}
                  className="h-8 text-sm"
                />
              )}
              <div className="space-y-1">
                <Label className="text-[10px] text-muted-foreground">Vertices JSON [[x,y],...]</Label>
                <textarea
                  value={zoneVerts}
                  onChange={(e) => setZoneVerts(e.target.value)}
                  className="w-full h-16 rounded-md border border-border bg-background text-xs font-mono px-2 py-1 text-foreground resize-none"
                  placeholder='[[x1,y1],[x2,y2],[x3,y3]]'
                />
              </div>
              <Button className="w-full gap-2" size="sm" onClick={onCreateZone}>
                <Layers className="h-4 w-4" /> Create Zone
              </Button>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
