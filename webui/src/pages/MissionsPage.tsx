import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, useCallback, Fragment } from "react";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { format } from "date-fns";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import DataTablePagination from "@/components/DataTablePagination";
import { Trash2, Search, ChevronDown, ChevronRight, Navigation, Timer, ParkingCircle, X, Filter } from "lucide-react";
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

/* ── Step details components ── */

const ACTION_ICON = { MOVE_TO: Navigation, WAIT: Timer, PARK: ParkingCircle } as const;
const ACTION_COLOR = { MOVE_TO: "text-blue-400", WAIT: "text-amber-400", PARK: "text-emerald-400" } as const;

function StepList({ steps }: { steps: any[] }) {
  return (
    <div className="space-y-0.5 py-1.5 px-2">
      {steps.map((step: any, i: number) => {
        const Icon = ACTION_ICON[step.action as keyof typeof ACTION_ICON] || Navigation;
        const color = ACTION_COLOR[step.action as keyof typeof ACTION_COLOR] || "text-muted-foreground";
        const coords = step.waypoint?.coordinates;
        return (
          <div key={step.stepId || i} className="flex items-center gap-1.5 py-0.5">
            <span className="text-[10px] text-muted-foreground/50 w-4 text-right tabular-nums">{i + 1}.</span>
            <Icon className={cn("h-3 w-3 shrink-0", color)} />
            <span className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground/80">{step.action}</span>
              {step.action === "MOVE_TO" && coords && (
                <span className="font-mono ml-1.5">({coords[0]?.toFixed(5)}, {coords[1]?.toFixed(5)})</span>
              )}
              {step.action === "WAIT" && step.duration != null && (
                <span className="ml-1.5">{step.duration}s</span>
              )}
              {step.action === "PARK" && step.zoneId && (
                <span className="ml-1.5">zone: {step.zoneId}</span>
              )}
              {step.action === "PARK" && !step.zoneId && (
                <span className="ml-1.5 text-muted-foreground/50">nearest</span>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function MissionStepDetails({ m, type }: { m: any; type: "regular" | "scheduled" }) {
  const cmd = m.command || {};
  const isAdvanced = cmd.command === "ADVANCED";

  if (isAdvanced) {
    const steps = type === "scheduled" ? (m.advancedSteps || cmd.steps) : cmd.steps;
    if (!steps || steps.length === 0)
      return <p className="text-xs text-muted-foreground/50 italic px-2 py-2">No step details</p>;
    return <StepList steps={steps} />;
  }

  // Simple MOVE_TO
  const coords = cmd.waypoints?.coordinates;
  if (!coords || (coords[0] === 0 && coords[1] === 0))
    return <p className="text-xs text-muted-foreground/50 italic px-2 py-2">No destination details</p>;
  return (
    <div className="flex items-center gap-1.5 px-2 py-2">
      <Navigation className="h-3 w-3 text-blue-400 shrink-0" />
      <span className="text-xs">
        <span className="font-medium text-foreground/80">MOVE_TO</span>
        <span className="font-mono ml-1.5 text-muted-foreground">({coords[0]?.toFixed(5)}, {coords[1]?.toFixed(5)})</span>
      </span>
    </div>
  );
}

function hasStepDetails(m: any): boolean {
  const cmd = m.command || {};
  if (cmd.command === "ADVANCED") return true;
  const coords = cmd.waypoints?.coordinates;
  return Boolean(coords && !(coords[0] === 0 && coords[1] === 0));
}

function missionTypeBadge(m: any) {
  const cmd = m.command || {};
  if (cmd.command === "ADVANCED") {
    const count = cmd.steps?.length || m.advancedSteps?.length || 0;
    return (
      <span className="text-[9px] px-1 py-0 rounded bg-purple-500/15 text-purple-400 border border-purple-500/20 leading-relaxed ml-1">
        ADV {count}
      </span>
    );
  }
  return null;
}

/* ── Mobile cards ── */

function MissionCard({ m, onDelete, expanded, onToggle }: { m: any; onDelete: () => void; expanded: boolean; onToggle: () => void }) {
  const id = m.command?.missionId || m.missionId;
  const expandable = hasStepDetails(m);
  return (
    <div className="border border-border rounded-lg bg-card">
      <div className="p-3 space-y-2 cursor-pointer" onClick={expandable ? onToggle : undefined}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            {expandable && (expanded
              ? <ChevronDown className="h-3 w-3 text-muted-foreground/60 shrink-0" />
              : <ChevronRight className="h-3 w-3 text-muted-foreground/60 shrink-0" />
            )}
            <span className="text-xs font-mono text-muted-foreground truncate max-w-[180px]">{id}</span>
            {missionTypeBadge(m)}
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className={cn("text-[10px]", statusColor(m.status))}>
              {m.status}
            </Badge>
            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={(e) => { e.stopPropagation(); onDelete(); }}>
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
      {expanded && (
        <div className="border-t border-border bg-secondary/20">
          <MissionStepDetails m={m} type="regular" />
        </div>
      )}
    </div>
  );
}

function ScheduledCard({ m, onDelete, expanded, onToggle }: { m: any; onDelete: () => void; expanded: boolean; onToggle: () => void }) {
  const id = m.command?.missionId || m.missionId;
  const expandable = hasStepDetails(m) || Boolean(m.advancedSteps?.length);
  return (
    <div className="border border-border rounded-lg bg-card">
      <div className="p-3 space-y-2 cursor-pointer" onClick={expandable ? onToggle : undefined}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            {expandable && (expanded
              ? <ChevronDown className="h-3 w-3 text-muted-foreground/60 shrink-0" />
              : <ChevronRight className="h-3 w-3 text-muted-foreground/60 shrink-0" />
            )}
            <span className="text-xs font-mono text-muted-foreground truncate max-w-[180px]">{id}</span>
            {missionTypeBadge(m)}
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className={cn("text-[10px]", statusColor(m.status))}>
              {m.status}
            </Badge>
            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={(e) => { e.stopPropagation(); onDelete(); }}>
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
      {expanded && (
        <div className="border-t border-border bg-secondary/20">
          <MissionStepDetails m={m} type="scheduled" />
        </div>
      )}
    </div>
  );
}

/* ── Main page ── */

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
  const [fStatus, setFStatus] = useState("all");
  const [fRobot, setFRobot] = useState("all");
  const [fType, setFType] = useState("all");
  const [fDateFrom, setFDateFrom] = useState<Date | undefined>(undefined);
  const [fDateTo, setFDateTo] = useState<Date | undefined>(undefined);
  const [page0, setPage0] = useState(0);
  const [rows0, setRows0] = useState(10);
  const [page1, setPage1] = useState(0);
  const [rows1, setRows1] = useState(10);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; type: "regular" | "scheduled" } | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const toggleExpand = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const hasFilters = fStatus !== "all" || fRobot !== "all" || fType !== "all" || fDateFrom || fDateTo || q;
  const clearFilters = () => {
    setQ(""); setFStatus("all"); setFRobot("all"); setFType("all"); setFDateFrom(undefined); setFDateTo(undefined);
    setPage0(0); setPage1(0);
  };

  // Collect unique values for filter dropdowns
  const allRegular = missionsData?.missions || [];
  const allScheduled = scheduledData?.missions || [];
  const robotIds = useMemo(() => {
    const s = new Set<string>();
    for (const m of allRegular) if (m.robotId) s.add(m.robotId);
    for (const m of allScheduled) if (m.robotId) s.add(m.robotId);
    return [...s].sort();
  }, [allRegular, allScheduled]);
  const statusValues = useMemo(() => {
    const s = new Set<string>();
    for (const m of allRegular) if (m.status) s.add(m.status);
    for (const m of allScheduled) if (m.status) s.add(m.status);
    return [...s].sort();
  }, [allRegular, allScheduled]);

  const applyFilters = useCallback((rows: any[], type: "regular" | "scheduled") => {
    const dateFrom = fDateFrom ? fDateFrom.getTime() : 0;
    const dateTo = fDateTo ? fDateTo.getTime() + 86400000 - 1 : Infinity; // end of day

    return rows.filter((r) => {
      // Text search
      if (q && !JSON.stringify(r).toLowerCase().includes(q.toLowerCase())) return false;
      // Status
      if (fStatus !== "all" && r.status !== fStatus) return false;
      // Robot
      if (fRobot !== "all" && r.robotId !== fRobot) return false;
      // Mission type (regular only)
      if (type === "regular" && fType !== "all") {
        const cmd = r.command?.command || "MOVE_TO";
        if (fType === "advanced" && cmd !== "ADVANCED") return false;
        if (fType === "simple" && cmd === "ADVANCED") return false;
      }
      // Date range
      const timeStr = type === "regular" ? r.sentTime : (r.scheduledTime || r.sentTime);
      if (timeStr && (dateFrom || dateTo < Infinity)) {
        const t = new Date(timeStr).getTime();
        if (t < dateFrom || t > dateTo) return false;
      }
      return true;
    });
  }, [q, fStatus, fRobot, fType, fDateFrom, fDateTo]);

  const missions = useMemo(
    () => applyFilters(allRegular, "regular"),
    [allRegular, applyFilters]
  );
  const scheduled = useMemo(
    () => applyFilters(allScheduled, "scheduled"),
    [allScheduled, applyFilters]
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
    <div className="p-3 sm:p-4 max-w-7xl mx-auto overflow-auto h-full">
      <h2 className="text-lg font-semibold mb-3">Mission History</h2>

      <Tabs defaultValue="regular">
        <div className="flex flex-col gap-2 mb-3">
          {/* Row 1: Tabs + search */}
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
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
                onChange={(e) => { setQ(e.target.value); setPage0(0); setPage1(0); }}
                className="pl-7 h-8 w-full sm:w-[200px] text-xs"
              />
            </div>
            {hasFilters && (
              <Button variant="ghost" size="sm" className="text-xs h-8 gap-1 text-muted-foreground" onClick={clearFilters}>
                <X className="h-3 w-3" /> Clear filters
              </Button>
            )}
          </div>
          {/* Row 2: Filters */}
          <div className="grid grid-cols-2 sm:flex sm:flex-wrap sm:items-center gap-2">
            <Select value={fStatus} onValueChange={(v) => { setFStatus(v); setPage0(0); setPage1(0); }}>
              <SelectTrigger className="h-8 w-full sm:w-[130px] text-xs">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {statusValues.map((s) => (
                  <SelectItem key={s} value={s}>{s}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={fRobot} onValueChange={(v) => { setFRobot(v); setPage0(0); setPage1(0); }}>
              <SelectTrigger className="h-8 w-full sm:w-[160px] text-xs">
                <SelectValue placeholder="Robot" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All robots</SelectItem>
                {robotIds.map((r) => (
                  <SelectItem key={r} value={r}>{r}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={fType} onValueChange={(v) => { setFType(v); setPage0(0); setPage1(0); }}>
              <SelectTrigger className="h-8 w-full sm:w-[130px] text-xs">
                <SelectValue placeholder="Type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All types</SelectItem>
                <SelectItem value="simple">MOVE_TO</SelectItem>
                <SelectItem value="advanced">Advanced</SelectItem>
              </SelectContent>
            </Select>
            <Popover>
              <PopoverTrigger className={cn("inline-flex items-center h-8 w-full sm:w-[130px] text-xs justify-start font-normal px-3 border rounded-md bg-background shadow-xs hover:bg-accent dark:border-input dark:bg-input/30 dark:hover:bg-input/50", !fDateFrom && "text-muted-foreground")}>
                {fDateFrom ? format(fDateFrom, "dd.MM.yyyy") : "From"}
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <Calendar mode="single" selected={fDateFrom} onSelect={(d) => { setFDateFrom(d); setPage0(0); setPage1(0); }} />
              </PopoverContent>
            </Popover>
            <Popover>
              <PopoverTrigger className={cn("inline-flex items-center h-8 w-full sm:w-[130px] text-xs justify-start font-normal px-3 border rounded-md bg-background shadow-xs hover:bg-accent dark:border-input dark:bg-input/30 dark:hover:bg-input/50", !fDateTo && "text-muted-foreground")}>
                {fDateTo ? format(fDateTo, "dd.MM.yyyy") : "To"}
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <Calendar mode="single" selected={fDateTo} onSelect={(d) => { setFDateTo(d); setPage0(0); setPage1(0); }} />
              </PopoverContent>
            </Popover>
          </div>
        </div>

        {/* Regular missions */}
        <TabsContent value="regular">
          {/* Mobile: cards */}
          <div className="space-y-2 md:hidden">
            {missions
              ?.slice(page0 * rows0, page0 * rows0 + rows0)
              .map((m: any) => {
                const id = m.command?.missionId || m.missionId;
                return (
                  <MissionCard
                    key={id}
                    m={m}
                    expanded={expandedIds.has(id)}
                    onToggle={() => toggleExpand(id)}
                    onDelete={() => setDeleteTarget({ id, type: "regular" })}
                  />
                );
              })}
          </div>
          {/* Desktop: table */}
          <div className="hidden md:block rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="text-xs w-8"></TableHead>
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
                  .map((m: any) => {
                    const id = m.command?.missionId || m.missionId;
                    const isExpanded = expandedIds.has(id);
                    const expandable = hasStepDetails(m);
                    return (
                      <Fragment key={id}>
                        <TableRow
                          className={cn(expandable && "cursor-pointer")}
                          onClick={expandable ? () => toggleExpand(id) : undefined}
                        >
                          <TableCell className="w-8 px-2">
                            {expandable && (isExpanded
                              ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground/60" />
                              : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/60" />
                            )}
                          </TableCell>
                          <TableCell className="text-xs font-mono">
                            <span className="flex items-center gap-1">
                              {id}{missionTypeBadge(m)}
                            </span>
                          </TableCell>
                          <TableCell className="text-xs">{m.robotId}</TableCell>
                          <TableCell className="text-xs">{m.command?.mapId || m.mapId}</TableCell>
                          <TableCell>
                            <Badge variant="outline" className={cn("text-[10px]", statusColor(m.status))}>
                              {m.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs font-mono text-muted-foreground">{m.sentTime || "\u2014"}</TableCell>
                          <TableCell className="text-xs font-mono text-muted-foreground">{m.executedTime || "\u2014"}</TableCell>
                          <TableCell className="text-xs font-mono text-muted-foreground">{m.completedTime || "\u2014"}</TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="ghost" size="icon"
                              className="h-7 w-7 text-muted-foreground hover:text-destructive"
                              onClick={(e) => { e.stopPropagation(); setDeleteTarget({ id, type: "regular" }); }}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </TableCell>
                        </TableRow>
                        {isExpanded && (
                          <TableRow className="hover:bg-transparent">
                            <TableCell colSpan={9} className="p-0 bg-secondary/20">
                              <MissionStepDetails m={m} type="regular" />
                            </TableCell>
                          </TableRow>
                        )}
                      </Fragment>
                    );
                  })}
              </TableBody>
            </Table>
          </div>
          <DataTablePagination
            count={missions?.length || 0}
            page={page0}
            rowsPerPage={rows0}
            onPageChange={setPage0}
            onRowsPerPageChange={(r) => { setRows0(r); setPage0(0); }}
          />
        </TabsContent>

        {/* Scheduled missions */}
        <TabsContent value="scheduled">
          {/* Mobile: cards */}
          <div className="space-y-2 md:hidden">
            {scheduled
              ?.slice(page1 * rows1, page1 * rows1 + rows1)
              .map((m: any) => {
                const id = m.command?.missionId || m.missionId;
                return (
                  <ScheduledCard
                    key={id}
                    m={m}
                    expanded={expandedIds.has(id)}
                    onToggle={() => toggleExpand(id)}
                    onDelete={() => setDeleteTarget({ id, type: "scheduled" })}
                  />
                );
              })}
          </div>
          {/* Desktop: table */}
          <div className="hidden md:block rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="text-xs w-8"></TableHead>
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
                  .map((m: any) => {
                    const id = m.command?.missionId || m.missionId;
                    const isExpanded = expandedIds.has(id);
                    const expandable = hasStepDetails(m) || Boolean(m.advancedSteps?.length);
                    return (
                      <Fragment key={id}>
                        <TableRow
                          className={cn(expandable && "cursor-pointer")}
                          onClick={expandable ? () => toggleExpand(id) : undefined}
                        >
                          <TableCell className="w-8 px-2">
                            {expandable && (isExpanded
                              ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground/60" />
                              : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/60" />
                            )}
                          </TableCell>
                          <TableCell className="text-xs font-mono">
                            <span className="flex items-center gap-1">
                              {id}{missionTypeBadge(m)}
                            </span>
                          </TableCell>
                          <TableCell className="text-xs">{m.robotId}</TableCell>
                          <TableCell className="text-xs">{m.command?.mapId || m.mapId}</TableCell>
                          <TableCell className="text-xs">{m.cron ? "CRON" : "Once"}</TableCell>
                          <TableCell>
                            <Badge variant="outline" className={cn("text-[10px]", statusColor(m.status))}>
                              {m.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs font-mono text-muted-foreground">{m.scheduledTime || m.cron || "\u2014"}</TableCell>
                          <TableCell className="text-xs font-mono text-muted-foreground">{m.executedTime || "\u2014"}</TableCell>
                          <TableCell className="text-xs font-mono text-muted-foreground">{m.completedTime || "\u2014"}</TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="ghost" size="icon"
                              className="h-7 w-7 text-muted-foreground hover:text-destructive"
                              onClick={(e) => { e.stopPropagation(); setDeleteTarget({ id, type: "scheduled" }); }}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </TableCell>
                        </TableRow>
                        {isExpanded && (
                          <TableRow className="hover:bg-transparent">
                            <TableCell colSpan={10} className="p-0 bg-secondary/20">
                              <MissionStepDetails m={m} type="scheduled" />
                            </TableCell>
                          </TableRow>
                        )}
                      </Fragment>
                    );
                  })}
              </TableBody>
            </Table>
          </div>
          <DataTablePagination
            count={scheduled?.length || 0}
            page={page1}
            rowsPerPage={rows1}
            onPageChange={setPage1}
            onRowsPerPageChange={(r) => { setRows1(r); setPage1(0); }}
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
