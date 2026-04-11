import { useQuery } from "@tanstack/react-query";
import { useSelectionStore } from "../utils/state";
import { fetchMaps, fetchRobots, stopRobot, fetchRobotAutoPark, updateRobotAutoPark } from "../utils/api";
import { useEffect, useRef, useState } from "react";
import { showToast } from "@/lib/toast";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { OctagonX, ParkingSquare } from "lucide-react";
import { cn } from "@/lib/utils";

export default function TopBanner() {
  const { data: robots } = useQuery({
    queryKey: ["robots"],
    queryFn: fetchRobots,
  });
  const { data: maps } = useQuery({ queryKey: ["maps"], queryFn: fetchMaps });
  const selectedRobotId = useSelectionStore((s) => s.selectedRobotId);
  const selectedMapId = useSelectionStore((s) => s.selectedMapId);
  const setSelectedRobotId = useSelectionStore((s) => s.setSelectedRobotId);
  const setSelectedMapId = useSelectionStore((s) => s.setSelectedMapId);
  const wsConnected = useSelectionStore((s) => s.wsConnected);
  const currentMissionId = useSelectionStore((s) => s.currentMissionId);
  const robotsStore = useSelectionStore((s) => s.robots);

  const robot =
    robotsStore?.find((r: any) => r.robotId === selectedRobotId) ||
    robots?.robots?.find((r: any) => r.robotId === selectedRobotId);

  const [tick, setTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(t);
  }, []);

  let isFresh = false;
  let secondsAgo: number | null = null;
  if (robot?.lastSeen) {
    const ts = Date.parse(robot.lastSeen);
    if (!Number.isNaN(ts)) {
      const diff = Date.now() - ts;
      isFresh = diff <= 10_000;
      secondsAgo = Math.max(0, Math.floor(diff / 1000));
    }
  }
  const robotStatus = isFresh ? "online" : "offline";

  const prevFreshRef = useRef<boolean | null>(null);
  const prevRobotRef = useRef<string | null>(null);
  useEffect(() => {
    const prevFresh = prevFreshRef.current;
    const prevRobot = prevRobotRef.current;
    if (selectedRobotId) {
      if (prevRobot === selectedRobotId && prevFresh === true && !isFresh) {
        showToast("Selected robot went offline (no updates in >10s)", "warning");
      }
      prevFreshRef.current = isFresh;
      prevRobotRef.current = selectedRobotId;
    } else {
      prevFreshRef.current = null;
      prevRobotRef.current = null;
    }
  }, [isFresh, selectedRobotId, tick]);

  const setRobots = useSelectionStore((s) => s.setRobots);
  useEffect(() => {
    if (robots?.robots) setRobots(robots.robots);
  }, [robots]);

  const [autoParkEnabled, setAutoParkEnabled] = useState(false);
  const [autoParkLoading, setAutoParkLoading] = useState(false);
  useEffect(() => {
    if (!selectedRobotId) {
      setAutoParkEnabled(false);
      return;
    }
    fetchRobotAutoPark(selectedRobotId)
      .then((res) => setAutoParkEnabled(res.enabled))
      .catch(() => setAutoParkEnabled(false));
  }, [selectedRobotId]);

  const onToggleAutoPark = async () => {
    if (!selectedRobotId) return;
    setAutoParkLoading(true);
    try {
      const res = await updateRobotAutoPark(selectedRobotId, !autoParkEnabled);
      setAutoParkEnabled(res.enabled);
      showToast(`Auto-park ${res.enabled ? "enabled" : "disabled"}`, "info");
    } catch (e: any) {
      showToast(e?.message || "Failed to toggle auto-park", "error");
    } finally {
      setAutoParkLoading(false);
    }
  };

  const onStop = async () => {
    if (!selectedRobotId) {
      showToast("Select a robot first", "warning");
      return;
    }
    try {
      await stopRobot(selectedRobotId);
      showToast("Stop command sent", "info");
    } catch (e: any) {
      showToast(e?.message || "Stop failed", "error");
    }
  };

  return (
    <div className="px-2 sm:px-3 py-2 space-y-2">
      {/* Row 1: Selectors + Stop */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground font-medium hidden sm:inline">Robot</span>
          <Select
            value={selectedRobotId || ""}
            onValueChange={setSelectedRobotId}
          >
            <SelectTrigger className="w-[130px] sm:w-[160px] h-8 text-xs bg-secondary/50">
              <SelectValue placeholder="Select robot" />
            </SelectTrigger>
            <SelectContent>
              {robots?.robots?.map((r: any) => (
                <SelectItem key={r.robotId} value={r.robotId}>
                  {r.name || r.robotId}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground font-medium hidden sm:inline">Map</span>
          <Select
            value={selectedMapId || ""}
            onValueChange={setSelectedMapId}
          >
            <SelectTrigger className="w-[130px] sm:w-[160px] h-8 text-xs bg-secondary/50">
              <SelectValue placeholder="Select map" />
            </SelectTrigger>
            <SelectContent>
              {maps?.maps?.map((m: any) => (
                <SelectItem key={m.mapId} value={m.mapId}>
                  {m.name || m.mapId}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Button
          variant="destructive"
          size="sm"
          className="h-8 sm:h-9 sm:px-4 gap-1.5"
          onClick={onStop}
        >
          <OctagonX className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
          <span className="hidden sm:inline text-sm">Stop / Abort</span>
          <span className="sm:hidden">Stop</span>
        </Button>

        {selectedRobotId && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className={cn(
                  "h-8 sm:h-9 sm:px-4 gap-1.5",
                  autoParkEnabled && "bg-success/20 border-success/30 text-success"
                )}
                onClick={onToggleAutoPark}
                disabled={autoParkLoading}
              >
                <ParkingSquare className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                <span className="hidden sm:inline text-sm">
                  {autoParkEnabled ? "Auto-Park On" : "Auto-Park Off"}
                </span>
                <span className="sm:hidden">
                  {autoParkEnabled ? "P" : "P"}
                </span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              Auto-park: robot goes to parking after 60s idle
            </TooltipContent>
          </Tooltip>
        )}
      </div>

      {/* Row 2: Status badges */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge
              className={cn(
                "text-[10px] font-mono",
                isFresh
                  ? "bg-success/20 text-success border-success/30 animate-pulse-glow"
                  : "bg-muted text-muted-foreground border-border"
              )}
              variant="outline"
            >
              <span
                className={cn(
                  "inline-block w-1.5 h-1.5 rounded-full mr-1",
                  isFresh ? "bg-success" : "bg-muted-foreground"
                )}
              />
              {robotStatus}
            </Badge>
          </TooltipTrigger>
          <TooltipContent>
            last seen {secondsAgo ?? "\u2014"}s ago
          </TooltipContent>
        </Tooltip>

        {robot && (
          <>
            <Badge variant="outline" className="text-[10px] font-mono">
              {robot.state ?? "\u2014"}
            </Badge>
            <Badge variant="outline" className="text-[10px] font-mono">
              Bat: {robot.batteryPct ?? "\u2014"}%
            </Badge>
            {Array.isArray(robot.position25832) &&
              robot.position25832.length >= 2 && (
                <Badge
                  variant="outline"
                  className="text-[10px] font-mono text-cyan hidden sm:inline-flex"
                >
                  {robot.position25832[0].toFixed(2)},{" "}
                  {robot.position25832[1].toFixed(2)}
                </Badge>
              )}
          </>
        )}

        <Badge
          variant="outline"
          className={cn(
            "text-[10px] font-mono",
            wsConnected
              ? "bg-success/20 text-success border-success/30"
              : "bg-muted text-muted-foreground border-border"
          )}
        >
          <span
            className={cn(
              "inline-block w-1.5 h-1.5 rounded-full mr-1",
              wsConnected ? "bg-success" : "bg-muted-foreground"
            )}
          />
          {wsConnected ? "WS" : "Disc"}
        </Badge>

        <Badge
          variant="outline"
          className="text-[10px] font-mono text-cyan border-cyan/30 hidden sm:inline-flex"
        >
          Mission: {currentMissionId || "\u2014"}
        </Badge>
      </div>
    </div>
  );
}
