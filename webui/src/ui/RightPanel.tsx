import { Box, Tab, Tabs, TextField, Button, Stack } from "@mui/material";
import { useState } from "react";
import { useSnackbar } from "notistack";
import { useSelectionStore } from "../utils/state";
import { sendMissionInstant, sendMissionScheduled } from "../utils/api";

export default function RightPanel() {
  const [tab, setTab] = useState(0);
  const { enqueueSnackbar } = useSnackbar();
  const robotId = useSelectionStore((s) => s.selectedRobotId);
  const mapId = useSelectionStore((s) => s.selectedMapId);
  const destX = useSelectionStore((s) => s.destX);
  const destY = useSelectionStore((s) => s.destY);
  const [scheduledTime, setScheduledTime] = useState("");
  const [cron, setCron] = useState("");

  const ready = Boolean(robotId && mapId && destX != null && destY != null);

  const onSendInstant = async () => {
    if (!ready) {
      enqueueSnackbar("Select robot, map, and a valid destination", {
        variant: "warning",
      });
      return;
    }
    try {
      await sendMissionInstant({
        robotId: robotId!,
        mapId: mapId!,
        x: destX!,
        y: destY!,
      });
      enqueueSnackbar("Mission sent", { variant: "success" });
    } catch (e: any) {
      enqueueSnackbar(e?.message || "Send failed", { variant: "error" });
    }
  };

  const onSendScheduled = async () => {
    if (!ready) {
      enqueueSnackbar("Select robot, map, and a valid destination", {
        variant: "warning",
      });
      return;
    }
    if (!scheduledTime && !cron) {
      enqueueSnackbar("Provide scheduled time or cron", { variant: "warning" });
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
      enqueueSnackbar("Scheduled mission created", { variant: "success" });
    } catch (e: any) {
      enqueueSnackbar(e?.message || "Schedule failed", { variant: "error" });
    }
  };
  return (
    <Box p={2}>
      <Tabs value={tab} onChange={(_, v) => setTab(v)}>
        <Tab label="Regular" />
        <Tab label="Scheduled" />
        <Tab label="CRON" />
      </Tabs>
      {tab === 0 && (
        <Stack spacing={1} mt={2}>
          <TextField
            size="small"
            label="X (EPSG:25832)"
            value={destX ?? ""}
            InputProps={{ readOnly: true }}
          />
          <TextField
            size="small"
            label="Y (EPSG:25832)"
            value={destY ?? ""}
            InputProps={{ readOnly: true }}
          />
          <Button variant="contained" onClick={onSendInstant} disabled={!ready}>
            Send
          </Button>
        </Stack>
      )}
      {tab === 1 && (
        <Stack spacing={1} mt={2}>
          <TextField
            size="small"
            label="X (EPSG:25832)"
            value={destX ?? ""}
            InputProps={{ readOnly: true }}
          />
          <TextField
            size="small"
            label="Y (EPSG:25832)"
            value={destY ?? ""}
            InputProps={{ readOnly: true }}
          />
          <TextField
            size="small"
            type="datetime-local"
            label="Scheduled time"
            InputLabelProps={{ shrink: true }}
            value={scheduledTime}
            onChange={(e) => setScheduledTime(e.target.value)}
          />
          <Button
            variant="contained"
            onClick={onSendScheduled}
            disabled={!ready}
          >
            Send
          </Button>
        </Stack>
      )}
      {tab === 2 && (
        <Stack spacing={1} mt={2}>
          <TextField
            size="small"
            label="X (EPSG:25832)"
            value={destX ?? ""}
            InputProps={{ readOnly: true }}
          />
          <TextField
            size="small"
            label="Y (EPSG:25832)"
            value={destY ?? ""}
            InputProps={{ readOnly: true }}
          />
          <TextField
            size="small"
            label="CRON (m h dom mon dow)"
            placeholder="0 9 * * *"
            value={cron}
            onChange={(e) => setCron(e.target.value)}
          />
          <Button
            variant="contained"
            onClick={onSendScheduled}
            disabled={!ready}
          >
            Send
          </Button>
        </Stack>
      )}
    </Box>
  );
}
