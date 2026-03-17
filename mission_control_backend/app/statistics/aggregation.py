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
    """Group missions by time period."""
    buckets: dict[str, dict] = defaultdict(lambda: {"completed": 0, "failed": 0, "total": 0})

    for m in missions:
        sent = _parse_time(m.sentTime)
        if not sent:
            continue
        key = _bucket_key(sent, period)
        buckets[key]["total"] += 1
        if m.status in ("completed", "failed"):
            buckets[key][m.status] += 1

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
