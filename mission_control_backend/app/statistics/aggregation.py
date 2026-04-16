from __future__ import annotations
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


def compute_mission_summary(missions: list) -> dict:
    """Total counts by status."""
    counts = defaultdict(int)
    for m in missions:
        counts[m.status] += 1
    return {
        "total": len(missions),
        "completed": counts.get("completed", 0),
        "failed": counts.get("failed", 0),
        "in_progress": counts.get("in_progress", 0),
        "cancelled": counts.get("cancelled", 0),
        "pending": counts.get("pending", 0),
    }


def compute_missions_over_time(missions: list, period: str = "day") -> list:
    """Group missions by time period with all status breakdowns."""
    buckets: dict[str, dict] = defaultdict(
        lambda: {"completed": 0, "failed": 0, "cancelled": 0, "in_progress": 0, "total": 0}
    )

    for m in missions:
        sent = _parse_time(m.sentTime)
        if not sent:
            continue
        key = _bucket_key(sent, period)
        buckets[key]["total"] += 1
        s = m.status
        if s in ("completed", "failed", "cancelled", "in_progress"):
            buckets[key][s] += 1

    return [{"period": k, **v} for k, v in sorted(buckets.items())]


def compute_duration_stats(missions: list) -> dict:
    """Average/min/max mission duration in seconds."""
    durations = []
    for m in missions:
        if m.status != "completed":
            continue
        start = _parse_time(m.executedTime) or _parse_time(m.sentTime)
        end = _parse_time(m.completedTime)
        if start and end:
            d = (end - start).total_seconds()
            if d > 0:
                durations.append(d)

    if not durations:
        return {"avg": 0, "min": 0, "max": 0, "count": 0}
    return {
        "avg": round(sum(durations) / len(durations), 1),
        "min": round(min(durations), 1),
        "max": round(max(durations), 1),
        "count": len(durations),
    }


def compute_robot_utilization(missions: list) -> list:
    """Per-robot mission count, success rate, avg duration."""
    robots: dict[str, dict] = defaultdict(
        lambda: {"total": 0, "completed": 0, "failed": 0, "durations": []}
    )

    for m in missions:
        rid = m.robotId
        robots[rid]["total"] += 1
        if m.status == "completed":
            robots[rid]["completed"] += 1
            start = _parse_time(m.executedTime) or _parse_time(m.sentTime)
            end = _parse_time(m.completedTime)
            if start and end:
                d = (end - start).total_seconds()
                if d > 0:
                    robots[rid]["durations"].append(d)
        elif m.status == "failed":
            robots[rid]["failed"] += 1

    result = []
    for rid, data in robots.items():
        denom = data["completed"] + data["failed"]
        success_rate = round(data["completed"] / denom * 100, 1) if denom > 0 else 0
        avg_dur = (
            round(sum(data["durations"]) / len(data["durations"]), 1)
            if data["durations"]
            else 0
        )
        result.append({
            "robotId": rid,
            "totalMissions": data["total"],
            "completed": data["completed"],
            "failed": data["failed"],
            "successRate": success_rate,
            "avgDuration": avg_dur,
        })
    return result


def compute_status_distribution(missions: list) -> list:
    """Status distribution for pie chart."""
    counts = defaultdict(int)
    for m in missions:
        counts[m.status] += 1
    return [{"status": k, "count": v} for k, v in counts.items()]


def compute_peak_hours(missions: list) -> list:
    """Missions grouped by hour-of-day."""
    hours = defaultdict(int)
    for m in missions:
        sent = _parse_time(m.sentTime)
        if sent:
            hours[sent.hour] += 1
    return [{"hour": h, "count": c} for h, c in sorted(hours.items())]


def compute_mission_type_breakdown(regular: list, scheduled: list) -> list:
    """Break down missions by type: Instant MOVE_TO, Advanced, Scheduled Once, Scheduled Recurring."""
    instant_simple = 0
    instant_advanced = 0
    sched_once = 0
    sched_recurring = 0

    for m in regular:
        cmd = m.command
        if hasattr(cmd, "command"):
            cmd_type = cmd.command
        elif isinstance(cmd, dict):
            cmd_type = cmd.get("command", "MOVE_TO")
        else:
            cmd_type = "MOVE_TO"

        if cmd_type == "ADVANCED":
            instant_advanced += 1
        else:
            instant_simple += 1

    for m in scheduled:
        if getattr(m, "scheduleType", "once") == "recurring" or getattr(m, "cron", None):
            sched_recurring += 1
        else:
            sched_once += 1

    return [
        {"type": "Instant", "count": instant_simple},
        {"type": "Advanced", "count": instant_advanced},
        {"type": "Scheduled", "count": sched_once},
        {"type": "Recurring", "count": sched_recurring},
    ]


def compute_map_usage(missions: list) -> list:
    """Count missions per map."""
    maps = defaultdict(int)
    for m in missions:
        cmd = m.command
        if hasattr(cmd, "mapId"):
            map_id = cmd.mapId
        elif isinstance(cmd, dict):
            map_id = cmd.get("mapId", "")
        else:
            map_id = ""
        if map_id:
            maps[map_id] += 1

    return sorted(
        [{"mapId": k, "count": v} for k, v in maps.items()],
        key=lambda x: x["count"],
        reverse=True,
    )


def compute_scheduled_summary(scheduled: list) -> dict:
    """Summary of scheduled missions."""
    by_status = defaultdict(int)
    once = 0
    recurring = 0
    for m in scheduled:
        by_status[m.status] += 1
        if getattr(m, "scheduleType", "once") == "recurring" or getattr(m, "cron", None):
            recurring += 1
        else:
            once += 1

    return {
        "total": len(scheduled),
        "byStatus": dict(by_status),
        "once": once,
        "recurring": recurring,
    }


def compute_peak_heatmap(missions: list) -> list:
    """Day-of-week x hour-of-day heatmap data."""
    grid = defaultdict(int)
    for m in missions:
        sent = _parse_time(m.sentTime)
        if sent:
            grid[(sent.weekday(), sent.hour)] += 1

    return [
        {"day": day, "hour": hour, "count": count}
        for (day, hour), count in sorted(grid.items())
    ]


# ── Helpers ──


def _parse_time(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    try:
        from dateutil import parser as dp
        return dp.isoparse(val)
    except Exception:
        return None


def _bucket_key(dt: datetime, period: str) -> str:
    if period == "year":
        return dt.strftime("%Y")
    if period == "month":
        return dt.strftime("%Y-%m")
    if period == "week":
        iso = dt.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    # default: day
    return dt.strftime("%Y-%m-%d")
