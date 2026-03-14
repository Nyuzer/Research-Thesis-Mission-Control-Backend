import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, useCallback } from "react";
import {
  deleteMission,
  deleteScheduledMission,
  fetchMissions,
  fetchScheduledMissions,
} from "../utils/api";
import { showToast } from "@/lib/toast";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import DataTablePagination from "@/components/DataTablePagination";
import { Trash2, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import ConfirmDeleteDialog from "@/components/ConfirmDeleteDialog";

function statusColor(status: string) {
  const s = status?.toLowerCase();
  if (s === "completed" || s === "done") return "bg-success/20 text-success border-success/30";
  if (s === "executing" || s === "running" || s === "in_progress")
    return "bg-cyan/20 text-cyan border-cyan/30";
  if (s === "failed" || s === "error") return "bg-destructive/20 text-destructive border-destructive/30";
  if (s === "pending" || s === "scheduled") return "bg-warning/20 text-warning border-warning/30";
  return "bg-muted text-muted-foreground border-border";
}

/* Mobile card for a single mission row */
function MissionCard({ m, onDelete }: { m: any; onDelete: () => void }) {
  const id = m.command?.missionId || m.missionId;
  return (
    <div className="border border-border rounded-lg p-3 space-y-2 bg-card">
      <div className="flex items-center justify-between">
        <span className="text-xs font-mono text-muted-foreground truncate max-w-[200px]">{id}</span>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className={cn("text-[10px]", statusColor(m.status))}>
            {m.status}
          </Badge>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground hover:text-destructive"
            onClick={onDelete}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <span className="text-muted-foreground">Robot</span>
        <span>{m.robotId}</span>
        <span className="text-muted-foreground">Map</span>
        <span>{m.command?.mapId || m.mapId}</span>
        <span className="text-muted-foreground">Sent</span>
        <span className="font-mono text-muted-foreground">{m.sentTime || "\u2014"}</span>
        <span className="text-muted-foreground">Done</span>
        <span className="font-mono text-muted-foreground">{m.completedTime || "\u2014"}</span>
      </div>
    </div>
  );
}

function ScheduledCard({ m, onDelete }: { m: any; onDelete: () => void }) {
  const id = m.command?.missionId || m.missionId;
  return (
    <div className="border border-border rounded-lg p-3 space-y-2 bg-card">
      <div className="flex items-center justify-between">
        <span className="text-xs font-mono text-muted-foreground truncate max-w-[200px]">{id}</span>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className={cn("text-[10px]", statusColor(m.status))}>
            {m.status}
          </Badge>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground hover:text-destructive"
            onClick={onDelete}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <span className="text-muted-foreground">Robot</span>
        <span>{m.robotId}</span>
        <span className="text-muted-foreground">Map</span>
        <span>{m.command?.mapId || m.mapId}</span>
        <span className="text-muted-foreground">Type</span>
        <span>{m.cron ? "CRON" : "Once"}</span>
        <span className="text-muted-foreground">Scheduled</span>
        <span className="font-mono text-muted-foreground">{m.scheduledTime || m.cron || "\u2014"}</span>
      </div>
    </div>
  );
}

export default function MissionsPage() {
  const { data: missionsData, refetch: refetchMissions } = useQuery({
    queryKey: ["missions"],
    queryFn: fetchMissions,
  });
  const { data: scheduledData, refetch: refetchScheduled } = useQuery({
    queryKey: ["scheduled-missions"],
    queryFn: fetchScheduledMissions,
  });
  const [q, setQ] = useState("");
  const [page0, setPage0] = useState(0);
  const [rows0, setRows0] = useState(10);
  const [page1, setPage1] = useState(0);
  const [rows1, setRows1] = useState(10);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; type: "regular" | "scheduled" } | null>(null);

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

  const onDeleteConfirmed = useCallback(async () => {
    if (!deleteTarget) return;
    try {
      if (deleteTarget.type === "regular") await deleteMission(deleteTarget.id);
      else await deleteScheduledMission(deleteTarget.id);
      showToast("Deleted", "success");
      refetchMissions();
      refetchScheduled();
    } catch (e: any) {
      showToast(e?.message || "Delete failed", "error");
    } finally {
      setDeleteTarget(null);
    }
  }, [deleteTarget, refetchMissions, refetchScheduled]);

  return (
    <div className="p-3 sm:p-4 max-w-7xl mx-auto">
      <h2 className="text-lg font-semibold mb-3">Mission History</h2>

      <Tabs defaultValue="regular">
        <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 mb-3">
          <TabsList className="bg-secondary/50 w-full sm:w-auto">
            <TabsTrigger value="regular" className="text-xs flex-1 sm:flex-none">
              Regular ({missions?.length ?? 0})
            </TabsTrigger>
            <TabsTrigger value="scheduled" className="text-xs flex-1 sm:flex-none">
              Scheduled ({scheduled?.length ?? 0})
            </TabsTrigger>
          </TabsList>
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder="Search..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="pl-7 h-8 w-full sm:w-[200px] text-xs"
            />
          </div>
        </div>

        {/* Regular missions */}
        <TabsContent value="regular">
          {/* Mobile: cards */}
          <div className="space-y-2 md:hidden">
            {missions
              ?.slice(page0 * rows0, page0 * rows0 + rows0)
              .map((m: any) => (
                <MissionCard
                  key={m.command?.missionId || m.missionId}
                  m={m}
                  onDelete={() =>
                    setDeleteTarget({
                      id: m.command?.missionId || m.missionId,
                      type: "regular",
                    })
                  }
                />
              ))}
          </div>
          {/* Desktop: table */}
          <div className="hidden md:block rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="text-xs">ID</TableHead>
                  <TableHead className="text-xs">Robot</TableHead>
                  <TableHead className="text-xs">Map</TableHead>
                  <TableHead className="text-xs">Status</TableHead>
                  <TableHead className="text-xs">Sent</TableHead>
                  <TableHead className="text-xs">Exec</TableHead>
                  <TableHead className="text-xs">Done</TableHead>
                  <TableHead className="text-xs text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {missions
                  ?.slice(page0 * rows0, page0 * rows0 + rows0)
                  .map((m: any) => (
                    <TableRow key={m.command?.missionId || m.missionId}>
                      <TableCell className="text-xs font-mono">
                        {m.command?.missionId || m.missionId}
                      </TableCell>
                      <TableCell className="text-xs">{m.robotId}</TableCell>
                      <TableCell className="text-xs">
                        {m.command?.mapId || m.mapId}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn("text-[10px]", statusColor(m.status))}
                        >
                          {m.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs font-mono text-muted-foreground">
                        {m.sentTime || "\u2014"}
                      </TableCell>
                      <TableCell className="text-xs font-mono text-muted-foreground">
                        {m.executedTime || "\u2014"}
                      </TableCell>
                      <TableCell className="text-xs font-mono text-muted-foreground">
                        {m.completedTime || "\u2014"}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-muted-foreground hover:text-destructive"
                          onClick={() =>
                            setDeleteTarget({
                              id: m.command?.missionId || m.missionId,
                              type: "regular",
                            })
                          }
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </div>
          <DataTablePagination
            count={missions?.length || 0}
            page={page0}
            rowsPerPage={rows0}
            onPageChange={setPage0}
            onRowsPerPageChange={(r) => {
              setRows0(r);
              setPage0(0);
            }}
          />
        </TabsContent>

        {/* Scheduled missions */}
        <TabsContent value="scheduled">
          {/* Mobile: cards */}
          <div className="space-y-2 md:hidden">
            {scheduled
              ?.slice(page1 * rows1, page1 * rows1 + rows1)
              .map((m: any) => (
                <ScheduledCard
                  key={m.command?.missionId || m.missionId}
                  m={m}
                  onDelete={() =>
                    setDeleteTarget({
                      id: m.command?.missionId || m.missionId,
                      type: "scheduled",
                    })
                  }
                />
              ))}
          </div>
          {/* Desktop: table */}
          <div className="hidden md:block rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="text-xs">ID</TableHead>
                  <TableHead className="text-xs">Robot</TableHead>
                  <TableHead className="text-xs">Map</TableHead>
                  <TableHead className="text-xs">Type</TableHead>
                  <TableHead className="text-xs">Status</TableHead>
                  <TableHead className="text-xs">Scheduled</TableHead>
                  <TableHead className="text-xs">Exec</TableHead>
                  <TableHead className="text-xs">Done</TableHead>
                  <TableHead className="text-xs text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {scheduled
                  ?.slice(page1 * rows1, page1 * rows1 + rows1)
                  .map((m: any) => (
                    <TableRow key={m.command?.missionId || m.missionId}>
                      <TableCell className="text-xs font-mono">
                        {m.command?.missionId || m.missionId}
                      </TableCell>
                      <TableCell className="text-xs">{m.robotId}</TableCell>
                      <TableCell className="text-xs">
                        {m.command?.mapId || m.mapId}
                      </TableCell>
                      <TableCell className="text-xs">
                        {m.cron ? "CRON" : "Once"}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn("text-[10px]", statusColor(m.status))}
                        >
                          {m.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs font-mono text-muted-foreground">
                        {m.scheduledTime || m.cron || "\u2014"}
                      </TableCell>
                      <TableCell className="text-xs font-mono text-muted-foreground">
                        {m.executedTime || "\u2014"}
                      </TableCell>
                      <TableCell className="text-xs font-mono text-muted-foreground">
                        {m.completedTime || "\u2014"}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-muted-foreground hover:text-destructive"
                          onClick={() =>
                            setDeleteTarget({
                              id: m.command?.missionId || m.missionId,
                              type: "scheduled",
                            })
                          }
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </div>
          <DataTablePagination
            count={scheduled?.length || 0}
            page={page1}
            rowsPerPage={rows1}
            onPageChange={setPage1}
            onRowsPerPageChange={(r) => {
              setRows1(r);
              setPage1(0);
            }}
          />
        </TabsContent>
      </Tabs>

      <ConfirmDeleteDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
        onConfirm={onDeleteConfirmed}
        title="Delete mission?"
        description="This will permanently delete this mission record. This action cannot be undone."
      />
    </div>
  );
}
