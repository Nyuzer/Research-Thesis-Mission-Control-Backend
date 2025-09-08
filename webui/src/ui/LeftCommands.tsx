import { Box, Button, Stack } from "@mui/material";
import { useSnackbar } from "notistack";
import { useSelectionStore } from "../utils/state";
import { stopRobot } from "../utils/api";

export default function LeftCommands() {
  const { enqueueSnackbar } = useSnackbar();
  const robotId = useSelectionStore((s) => s.selectedRobotId);

  const onStop = async () => {
    if (!robotId) {
      enqueueSnackbar("Select a robot first", { variant: "warning" });
      return;
    }
    try {
      await stopRobot(robotId);
      enqueueSnackbar("Stop command sent", { variant: "info" });
    } catch (e: any) {
      enqueueSnackbar(e?.message || "Stop failed", { variant: "error" });
    }
  };

  return (
    <Box p={2}>
      <Stack spacing={1}>
        <Button variant="outlined" color="error" onClick={onStop}>
          Stop / Abort
        </Button>
      </Stack>
    </Box>
  );
}
