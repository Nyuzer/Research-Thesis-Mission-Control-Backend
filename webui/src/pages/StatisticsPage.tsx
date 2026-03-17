import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchJSON } from "@/utils/api";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, Legend,
} from "recharts";
import { Activity, CheckCircle, XCircle, Clock, TrendingUp } from "lucide-react";

const COLORS = ["#06b6d4", "#22c55e", "#ef4444", "#f59e0b", "#8b5cf6", "#ec4899"];
const STATUS_COLORS: Record<string, string> = {
  completed: "#22c55e",
  failed: "#ef4444",
  in_progress: "#06b6d4",
  pending: "#f59e0b",
  cancelled: "#6b7280",
};

type Period = "day" | "week" | "month" | "year";

export default function StatisticsPage() {
  const [period, setPeriod] = useState<Period>("day");

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

  const summary = overview?.summary;
  const duration = overview?.duration;
  const statusDist = overview?.statusDistribution || [];
  const robotUtil = overview?.robotUtilization || [];
  const peakHours = overview?.peakHours || [];

  const successRate =
    summary && summary.completed + summary.failed > 0
      ? Math.round((summary.completed / (summary.completed + summary.failed)) * 100)
      : 0;

  return (
    <div className="p-4 sm:p-6 space-y-6 overflow-auto h-full">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <KpiCard
          label="Total Missions"
          value={summary?.total ?? "--"}
          icon={<Activity className="h-4 w-4 text-cyan" />}
        />
        <KpiCard
          label="Completed"
          value={summary?.completed ?? "--"}
          icon={<CheckCircle className="h-4 w-4 text-green-400" />}
        />
        <KpiCard
          label="Failed"
          value={summary?.failed ?? "--"}
          icon={<XCircle className="h-4 w-4 text-red-400" />}
        />
        <KpiCard
          label="Success Rate"
          value={`${successRate}%`}
          icon={<TrendingUp className="h-4 w-4 text-cyan" />}
        />
      </div>

      {/* Duration stats */}
      {duration && duration.count > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <KpiCard label="Avg Duration" value={`${duration.avg}s`} icon={<Clock className="h-4 w-4 text-muted-foreground" />} />
          <KpiCard label="Min Duration" value={`${duration.min}s`} icon={<Clock className="h-4 w-4 text-muted-foreground" />} />
          <KpiCard label="Max Duration" value={`${duration.max}s`} icon={<Clock className="h-4 w-4 text-muted-foreground" />} />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Missions Over Time */}
        <div className="bg-card border border-border rounded-xl p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-foreground">Missions Over Time</h3>
            <div className="flex gap-1">
              {(["day", "week", "month", "year"] as Period[]).map((p) => (
                <button
                  key={p}
                  onClick={() => setPeriod(p)}
                  className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                    period === p
                      ? "bg-primary/15 text-primary"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={overTime || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="period" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
              <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
              <Tooltip
                contentStyle={{
                  background: "var(--card)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  color: "var(--foreground)",
                }}
              />
              <Bar dataKey="completed" fill="#22c55e" radius={[4, 4, 0, 0]} />
              <Bar dataKey="failed" fill="#ef4444" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Status Distribution Pie */}
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-sm font-semibold text-foreground mb-4">Status Distribution</h3>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie
                data={statusDist}
                dataKey="count"
                nameKey="status"
                cx="50%"
                cy="50%"
                outerRadius={90}
                innerRadius={50}
                paddingAngle={2}
                label={({ name, value }) => `${name}: ${value}`}
              >
                {statusDist.map((entry: any, i: number) => (
                  <Cell key={i} fill={STATUS_COLORS[entry.status] || COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Peak Hours */}
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-sm font-semibold text-foreground mb-4">Peak Hours</h3>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={peakHours}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey="hour"
                tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                tickFormatter={(h) => `${h}:00`}
              />
              <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
              <Tooltip
                contentStyle={{
                  background: "var(--card)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  color: "var(--foreground)",
                }}
              />
              <Line type="monotone" dataKey="count" stroke="#06b6d4" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Robot Utilization Table */}
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-sm font-semibold text-foreground mb-4">Robot Utilization</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-muted-foreground text-left border-b border-border">
                  <th className="pb-2 font-medium">Robot</th>
                  <th className="pb-2 font-medium">Total</th>
                  <th className="pb-2 font-medium">Success</th>
                  <th className="pb-2 font-medium">Avg Dur</th>
                </tr>
              </thead>
              <tbody>
                {robotUtil.map((r: any) => (
                  <tr key={r.robotId} className="border-b border-border last:border-0">
                    <td className="py-2 text-foreground font-medium">{r.robotId}</td>
                    <td className="py-2 text-muted-foreground">{r.totalMissions}</td>
                    <td className="py-2">
                      <span className={r.successRate >= 80 ? "text-green-400" : r.successRate >= 50 ? "text-yellow-400" : "text-red-400"}>
                        {r.successRate}%
                      </span>
                    </td>
                    <td className="py-2 text-muted-foreground">{r.avgDuration}s</td>
                  </tr>
                ))}
                {robotUtil.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-4 text-center text-muted-foreground">
                      No robot data available
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function KpiCard({ label, value, icon }: { label: string; value: string | number; icon: React.ReactNode }) {
  return (
    <div className="bg-card border border-border rounded-xl p-3 sm:p-4">
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>
      <p className="text-xl sm:text-2xl font-bold text-foreground">{value}</p>
    </div>
  );
}
