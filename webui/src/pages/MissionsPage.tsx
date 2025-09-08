import {
  Box,
  Typography,
  TextField,
  Tabs,
  Tab,
  IconButton,
  Chip,
  Stack,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  TablePagination,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  deleteMission,
  deleteScheduledMission,
  fetchMissions,
  fetchScheduledMissions,
} from "../utils/api";
import { useSnackbar } from "notistack";
import DeleteIcon from "@mui/icons-material/Delete";

export default function MissionsPage() {
  const { data: missionsData, refetch: refetchMissions } = useQuery({
    queryKey: ["missions"],
    queryFn: fetchMissions,
  });
  const { data: scheduledData, refetch: refetchScheduled } = useQuery({
    queryKey: ["scheduled-missions"],
    queryFn: fetchScheduledMissions,
  });
  const [tab, setTab] = useState(0);
  const [q, setQ] = useState("");
  const { enqueueSnackbar } = useSnackbar();
  const [page0, setPage0] = useState(0);
  const [rows0, setRows0] = useState(10);
  const [page1, setPage1] = useState(0);
  const [rows1, setRows1] = useState(10);

  const filterRows = (rows: any[] = []) =>
    rows.filter((r) =>
      JSON.stringify(r).toLowerCase().includes(q.toLowerCase())
    );

  const missions = useMemo(
    () => filterRows(missionsData?.missions),
    [missionsData, q]
  );
  const scheduled = useMemo(
    () => filterRows(scheduledData?.missions),
    [scheduledData, q]
  );

  const onDelete = async (id: string, type: "regular" | "scheduled") => {
    try {
      if (type === "regular") await deleteMission(id);
      else await deleteScheduledMission(id);
      enqueueSnackbar("Deleted", { variant: "success" });
      refetchMissions();
      refetchScheduled();
    } catch (e: any) {
      enqueueSnackbar(e?.message || "Delete failed", { variant: "error" });
    }
  };

  return (
    <Box p={2}>
      <Typography variant="h5" mb={1}>
        Mission History
      </Typography>
      <Stack direction="row" spacing={1} alignItems="center" mb={1}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}>
          <Tab label={`Regular (${missions?.length ?? 0})`} />
          <Tab label={`Scheduled (${scheduled?.length ?? 0})`} />
        </Tabs>
        <TextField
          size="small"
          placeholder="Search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </Stack>

      {tab === 0 && (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>Robot</TableCell>
              <TableCell>Map</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Sent</TableCell>
              <TableCell>Exec</TableCell>
              <TableCell>Done</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {missions
              ?.slice(page0 * rows0, page0 * rows0 + rows0)
              .map((m: any) => (
                <TableRow key={m.command?.missionId || m.missionId} hover>
                  <TableCell>{m.command?.missionId || m.missionId}</TableCell>
                  <TableCell>{m.robotId}</TableCell>
                  <TableCell>{m.command?.mapId || m.mapId}</TableCell>
                  <TableCell>
                    <Chip size="small" label={m.status} />
                  </TableCell>
                  <TableCell>{m.sentTime || "—"}</TableCell>
                  <TableCell>{m.executedTime || "—"}</TableCell>
                  <TableCell>{m.completedTime || "—"}</TableCell>
                  <TableCell align="right">
                    <IconButton
                      size="small"
                      onClick={() =>
                        onDelete(m.command?.missionId || m.missionId, "regular")
                      }
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      )}
      {tab === 0 && (
        <TablePagination
          component="div"
          count={missions?.length || 0}
          page={page0}
          onPageChange={(_, p) => setPage0(p)}
          rowsPerPage={rows0}
          onRowsPerPageChange={(e) => {
            setRows0(parseInt(e.target.value, 10));
            setPage0(0);
          }}
          rowsPerPageOptions={[5, 10, 25, 50]}
        />
      )}

      {tab === 1 && (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>Robot</TableCell>
              <TableCell>Map</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Scheduled</TableCell>
              <TableCell>Exec</TableCell>
              <TableCell>Done</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {scheduled
              ?.slice(page1 * rows1, page1 * rows1 + rows1)
              .map((m: any) => (
                <TableRow key={m.command?.missionId || m.missionId} hover>
                  <TableCell>{m.command?.missionId || m.missionId}</TableCell>
                  <TableCell>{m.robotId}</TableCell>
                  <TableCell>{m.command?.mapId || m.mapId}</TableCell>
                  <TableCell>{m.cron ? "CRON" : "Once"}</TableCell>
                  <TableCell>
                    <Chip size="small" label={m.status} />
                  </TableCell>
                  <TableCell>{m.scheduledTime || m.cron || "—"}</TableCell>
                  <TableCell>{m.executedTime || "—"}</TableCell>
                  <TableCell>{m.completedTime || "—"}</TableCell>
                  <TableCell align="right">
                    <IconButton
                      size="small"
                      onClick={() =>
                        onDelete(
                          m.command?.missionId || m.missionId,
                          "scheduled"
                        )
                      }
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      )}
      {tab === 1 && (
        <TablePagination
          component="div"
          count={scheduled?.length || 0}
          page={page1}
          onPageChange={(_, p) => setPage1(p)}
          rowsPerPage={rows1}
          onRowsPerPageChange={(e) => {
            setRows1(parseInt(e.target.value, 10));
            setPage1(0);
          }}
          rowsPerPageOptions={[5, 10, 25, 50]}
        />
      )}
    </Box>
  );
}
