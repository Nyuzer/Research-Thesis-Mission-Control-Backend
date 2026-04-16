import { useState, useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchJSON, fetchMaps } from "@/utils/api";
import { useSelectionStore } from "@/utils/state";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, Legend,
} from "recharts";
import {
  TrendingUp, Clock, Wifi, CalendarClock, Navigation, Timer,
  ParkingCircle, Map, Bot,
} from "lucide-react";

const COLORS = ["#06b6d4", "#22c55e", "#ef4444", "#f59e0b", "#8b5cf6", "#ec4899"];
const STATUS_COLORS: Record<string, string> = {
  completed: "#22c55e",
  failed: "#ef4444",
  in_progress: "#06b6d4",
  sent: "#06b6d4",
  pending: "#f59e0b",
  scheduled: "#f59e0b",
  cancelled: "#6b7280",
  expired: "#4b5563",
};
const TYPE_COLORS: Record<string, string> = {
  Instant: "#06b6d4",
  Advanced: "#8b5cf6",
  Scheduled: "#f59e0b",
  Recurring: "#ec4899",
};
const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

type Period = "day" | "week" | "month" | "year";

function fmtDuration(seconds: number): string {
  if (seconds <= 0) return "0s";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m === 0) return `${s}s`;
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

const tooltipStyle = {
  background: "var(--card)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  color: "var(--foreground)",
};

export default function StatisticsPage() {
  const [period, setPeriod] = useState<Period>("day");
  const robots = useSelectionStore((s) => s.robots);

  const { data: overview } = useQuery({
    queryKey: ["statistics", "overview"],
    queryFn: () => fetchJSON<any>("/api/statistics/overview"),
    refetchInterval: 30000,
  });

  const { data: overTime } = useQuery({
    queryKey: ["statistics", "over-time", period],
    queryFn: () => fetchJSON<any[]>(`/api/statistics/missions/over-time?period=${period}`),
    refetchInterval: 30000,
  });

  const { data: mapsData } = useQuery({
    queryKey: ["maps"],
    queryFn: fetchMaps,
  });

  const summary = overview?.summary;
  const duration = overview?.duration;
  const statusDist = overview?.statusDistribution || [];
  const robotUtil = overview?.robotUtilization || [];
  const peakHours = overview?.peakHours || [];
  const missionTypes = overview?.missionTypeBreakdown || [];
  const mapUsageRaw = overview?.mapUsage || [];
  const mapNameById = useMemo(() => {
    const m: Record<string, string> = {};
    for (const map of mapsData?.maps || []) {
      if (map.name) m[map.mapId] = map.name;
    }
    return m;
  }, [mapsData]);
  const mapUsage = mapUsageRaw.map((e: any) => ({
    ...e,
    label: mapNameById[e.mapId] || e.mapId,
  }));
  const scheduledSummary = overview?.scheduledSummary;
  const peakHeatmap = overview?.peakHeatmap || [];

  const successRate =
    summary && summary.completed + summary.failed > 0
      ? Math.round((summary.completed / (summary.completed + summary.failed)) * 100)
      : 0;

  const onlineRobots = robots.filter((r: any) => r.online).length;
  const totalRobots = robots.length;
  const pendingScheduled = scheduledSummary?.byStatus?.scheduled || 0;

  // Build heatmap grid (7 days x 24 hours)
  const heatmapGrid: number[][] = Array.from({ length: 7 }, () => Array(24).fill(0));
  let heatmapMax = 0;
  for (const d of peakHeatmap) {
    if (d.day >= 0 && d.day < 7 && d.hour >= 0 && d.hour < 24) {
      heatmapGrid[d.day][d.hour] = d.count;
      if (d.count > heatmapMax) heatmapMax = d.count;
    }
  }

  const [heatmapHover, setHeatmapHover] = useState<{ day: number; hour: number; count: number; x: number; y: number } | null>(null);

  return (
    <div className="p-4 sm:p-6 space-y-6 overflow-auto h-full select-none">
      {/* KPI Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <KpiCard
          label="Success Rate"
          value={`${successRate}%`}
          sub={summary ? `${summary.completed}/${summary.completed + summary.failed}` : undefined}
          icon={<TrendingUp className="h-4 w-4 text-green-400" />}
          color={successRate >= 80 ? "text-green-400" : successRate >= 50 ? "text-amber-400" : "text-red-400"}
        />
        <KpiCard
          label="Avg Duration"
          value={duration?.count > 0 ? fmtDuration(duration.avg) : "--"}
          sub={duration?.count > 0 ? `min ${fmtDuration(duration.min)} / max ${fmtDuration(duration.max)}` : undefined}
          icon={<Clock className="h-4 w-4 text-cyan-400" />}
        />
        <KpiCard
          label="Fleet Online"
          value={`${onlineRobots}/${totalRobots}`}
          sub={totalRobots > 0 ? `${Math.round((onlineRobots / totalRobots) * 100)}% online` : "no robots"}
          icon={<Wifi className="h-4 w-4 text-emerald-400" />}
          color={onlineRobots === totalRobots ? "text-emerald-400" : "text-amber-400"}
        />
        <KpiCard
          label="Pending Scheduled"
          value={pendingScheduled}
          sub={scheduledSummary ? `${scheduledSummary.total} total scheduled` : undefined}
          icon={<CalendarClock className="h-4 w-4 text-amber-400" />}
        />
      </div>

      {/* Row 1: Missions Over Time + Status Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard
          title="Missions Over Time"
          action={
            <div className="flex gap-1">
              {(["day", "week", "month", "year"] as Period[]).map((p) => (
                <button
                  key={p}
                  onClick={() => setPeriod(p)}
                  className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                    period === p ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          }
        >
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={overTime || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="period" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
              <YAxis tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="completed" stackId="a" fill="#22c55e" />
              <Bar dataKey="failed" stackId="a" fill="#ef4444" />
              <Bar dataKey="cancelled" stackId="a" fill="#6b7280" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Status Distribution">
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={statusDist}
                dataKey="count"
                nameKey="status"
                cx="50%"
                cy="50%"
                outerRadius={85}
                innerRadius={48}
                paddingAngle={2}
                stroke="none"
                isAnimationActive={false}
              >
                {statusDist.map((entry: any, i: number) => (
                  <Cell key={i} fill={STATUS_COLORS[entry.status] || COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 11 }} formatter={(value: string, entry: any) => `${value}: ${entry.payload.count}`} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Row 2: Mission Type + Map Usage */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard title="Mission Types">
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={missionTypes.filter((t: any) => t.count > 0)}
                dataKey="count"
                nameKey="type"
                cx="50%"
                cy="50%"
                outerRadius={85}
                innerRadius={48}
                paddingAngle={2}
                stroke="none"
                isAnimationActive={false}
              >
                {missionTypes.filter((t: any) => t.count > 0).map((entry: any, i: number) => (
                  <Cell key={i} fill={TYPE_COLORS[entry.type] || COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 11 }} formatter={(value: string, entry: any) => `${value}: ${entry.payload.count}`} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Map Usage">
          {mapUsage.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={mapUsage} layout="vertical" margin={{ left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis type="number" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
                <YAxis
                  dataKey="label"
                  type="category"
                  tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
                  width={100}
                  tickFormatter={(v: string) => v.length > 14 ? v.slice(0, 14) + "..." : v}
                />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="count" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState />
          )}
        </ChartCard>
      </div>

      {/* Row 3: Peak Heatmap + Robot Utilization */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard title="Activity Heatmap">
          {peakHeatmap.length > 0 ? (
            <div className="overflow-hidden relative" onMouseLeave={() => setHeatmapHover(null)}>
              <p className="text-[10px] text-muted-foreground/40 mb-2">Missions aggregated by day of week and hour (all time)</p>
              <div className="min-w-[500px]">
                {/* Hour labels */}
                <div className="flex ml-10 mb-1">
                  {Array.from({ length: 24 }, (_, h) => (
                    <span key={h} className="flex-1 text-center text-[9px] text-muted-foreground/50">
                      {h % 3 === 0 ? `${h}` : ""}
                    </span>
                  ))}
                </div>
                {/* Grid rows */}
                {DAY_NAMES.map((day, di) => (
                  <div key={di} className="flex items-center gap-1 mb-0.5">
                    <span className="w-9 text-[10px] text-muted-foreground text-right shrink-0">{day}</span>
                    <div className="flex flex-1 gap-0.5">
                      {heatmapGrid[di].map((count, hi) => {
                        const intensity = heatmapMax > 0 ? count / heatmapMax : 0;
                        return (
                          <div
                            key={hi}
                            className="flex-1 aspect-square rounded-sm cursor-crosshair"
                            style={{
                              backgroundColor: count === 0
                                ? "var(--secondary)"
                                : `rgba(6, 182, 212, ${0.15 + intensity * 0.85})`,
                            }}
                            onMouseEnter={(e) => {
                              const rect = e.currentTarget.getBoundingClientRect();
                              const parent = e.currentTarget.closest(".relative")!.getBoundingClientRect();
                              setHeatmapHover({
                                day: di, hour: hi, count,
                                x: rect.left - parent.left + rect.width / 2,
                                y: rect.top - parent.top - 4,
                              });
                            }}
                            onMouseLeave={() => setHeatmapHover(null)}
                          />
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
              {/* Tooltip */}
              {heatmapHover && (
                <div
                  className="absolute pointer-events-none z-10 px-2 py-1 rounded-md text-xs bg-card border border-border shadow-lg whitespace-nowrap"
                  style={{
                    left: `clamp(60px, ${heatmapHover.x}px, calc(100% - 60px))`,
                    top: heatmapHover.y,
                    transform: "translate(-50%, -100%)",
                  }}
                >
                  <span className="font-medium">{DAY_NAMES[heatmapHover.day]} {heatmapHover.hour}:00</span>
                  <span className="text-muted-foreground ml-1.5">{heatmapHover.count} mission{heatmapHover.count !== 1 ? "s" : ""}</span>
                </div>
              )}
            </div>
          ) : (
            <EmptyState />
          )}
        </ChartCard>

        <ChartCard title="Robot Utilization">
          {robotUtil.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={robotUtil} layout="vertical" margin={{ left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis type="number" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
                <YAxis
                  dataKey="robotId"
                  type="category"
                  tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
                  width={120}
                  tickFormatter={(v: string) => v.length > 16 ? v.slice(0, 16) + "..." : v}
                />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="completed" stackId="a" fill="#22c55e" />
                <Bar dataKey="failed" stackId="a" fill="#ef4444" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState />
          )}
        </ChartCard>
      </div>

      {/* Row 4: Peak Hours + Fleet Status */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard title="Peak Hours">
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={peakHours}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="hour" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} tickFormatter={(h) => `${h}:00`} />
              <YAxis tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Line type="monotone" dataKey="count" stroke="#06b6d4" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Fleet Battery">
          {robots.length > 0 ? (
            <div className="space-y-2 py-1">
              {robots.map((r: any) => {
                const pct = r.batteryPct ?? 0;
                const color = pct >= 60 ? "bg-emerald-500" : pct >= 30 ? "bg-amber-500" : "bg-red-500";
                return (
                  <div key={r.robotId} className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground w-28 truncate shrink-0">{r.name || r.robotId}</span>
                    <div className="flex-1 h-4 bg-secondary rounded-full overflow-hidden">
                      <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
                    </div>
                    <span className="text-xs font-mono text-muted-foreground w-10 text-right">
                      {pct != null ? `${Math.round(pct)}%` : "--"}
                    </span>
                    <span className={`w-2 h-2 rounded-full shrink-0 ${r.online ? "bg-emerald-400" : "bg-zinc-600"}`} />
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState text="No robots connected" />
          )}
        </ChartCard>
      </div>
    </div>
  );
}

/* ── Reusable components ── */

function KpiCard({ label, value, sub, icon, color }: {
  label: string;
  value: string | number;
  sub?: string;
  icon: React.ReactNode;
  color?: string;
}) {
  return (
    <div className="bg-card border border-border rounded-xl p-3 sm:p-4">
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <span className="text-[10px] text-muted-foreground uppercase tracking-wider">{label}</span>
      </div>
      <p className={`text-xl sm:text-2xl font-bold ${color || "text-foreground"}`}>{value}</p>
      {sub && <p className="text-[10px] text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}

function ChartCard({ title, action, children }: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-card border border-border rounded-xl p-4 [&_*]:outline-none">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        {action}
      </div>
      {children}
    </div>
  );
}

function EmptyState({ text }: { text?: string }) {
  return (
    <div className="flex items-center justify-center h-32 text-xs text-muted-foreground/50">
      {text || "No data available"}
    </div>
  );
}
