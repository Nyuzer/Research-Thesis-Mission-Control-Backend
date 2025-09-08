import {
  Box,
  Chip,
  MenuItem,
  Select,
  Stack,
  Typography,
  Tooltip,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useSelectionStore } from "../utils/state";
import { fetchMaps, fetchRobots } from "../utils/api";
import { useEffect, useRef, useState } from "react";
import { useSnackbar } from "notistack";

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
  const { enqueueSnackbar } = useSnackbar();

  const robot =
    robotsStore?.find((r: any) => r.robotId === selectedRobotId) ||
    robots?.robots?.find((r: any) => r.robotId === selectedRobotId);
  // Consider robot online if lastSeen is within 10 seconds
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

  // Warn when selected robot transitions to offline
  const prevFreshRef = useRef<boolean | null>(null);
  const prevRobotRef = useRef<string | null>(null);
  useEffect(() => {
    const prevFresh = prevFreshRef.current;
    const prevRobot = prevRobotRef.current;
    if (selectedRobotId) {
      if (prevRobot === selectedRobotId && prevFresh === true && !isFresh) {
        enqueueSnackbar("Selected robot went offline (no updates in >10s)", {
          variant: "warning",
        });
      }
      prevFreshRef.current = isFresh;
      prevRobotRef.current = selectedRobotId;
    } else {
      prevFreshRef.current = null;
      prevRobotRef.current = null;
    }
  }, [isFresh, selectedRobotId, tick]);

  // Reflect robots into global store for MapView
  const setRobots = useSelectionStore((s) => s.setRobots);
  useEffect(() => {
    if (robots?.robots) setRobots(robots.robots);
  }, [robots]);

  return (
    <Box p={1} display="flex" alignItems="center" gap={2}>
      <Stack direction="row" alignItems="center" gap={1}>
        <Typography variant="body2">Robot:</Typography>
        <Select
          size="small"
          value={selectedRobotId || ""}
          onChange={(e) => setSelectedRobotId(e.target.value)}
          displayEmpty
        >
          <MenuItem value="">
            <em>Select robot</em>
          </MenuItem>
          {robots?.robots?.map((r: any) => (
            <MenuItem key={r.robotId} value={r.robotId}>
              {r.name || r.robotId}
            </MenuItem>
          ))}
        </Select>
      </Stack>
      <Stack direction="row" alignItems="center" gap={1}>
        <Typography variant="body2">Map:</Typography>
        <Select
          size="small"
          value={selectedMapId || ""}
          onChange={(e) => setSelectedMapId(e.target.value)}
          displayEmpty
        >
          <MenuItem value="">
            <em>Select map</em>
          </MenuItem>
          {maps?.maps?.map((m: any) => (
            <MenuItem key={m.mapId} value={m.mapId}>
              {m.name || m.mapId}
            </MenuItem>
          ))}
        </Select>
      </Stack>
      <Tooltip
        title={`last seen ${secondsAgo ?? "—"}s ago`}
        placement="bottom"
        disableInteractive
      >
        <Chip
          label={`Status: ${robotStatus}`}
          color={isFresh ? "success" : "default"}
          size="small"
        />
      </Tooltip>
      {robot && (
        <>
          <Chip label={`State: ${robot.state ?? "—"}`} size="small" />
          <Chip label={`Battery: ${robot.batteryPct ?? "—"}%`} size="small" />
          {Array.isArray(robot.position25832) &&
            robot.position25832.length >= 2 && (
              <Chip
                label={`Pos: ${robot.position25832[0].toFixed(
                  2
                )}, ${robot.position25832[1].toFixed(2)}`}
                size="small"
              />
            )}
        </>
      )}
      <Chip
        label={wsConnected ? "Connected" : "Disconnected"}
        color={wsConnected ? "success" : "default"}
        size="small"
      />
      <Chip label={`Mission: ${currentMissionId || "—"}`} size="small" />
    </Box>
  );
}
