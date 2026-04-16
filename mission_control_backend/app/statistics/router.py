from fastapi import APIRouter, Depends, Query
import logging

from app.auth.dependencies import get_current_user
from app.auth.models import UserResponse
from .aggregation import (
    compute_mission_summary,
    compute_missions_over_time,
    compute_duration_stats,
    compute_robot_utilization,
    compute_status_distribution,
    compute_peak_hours,
    compute_mission_type_breakdown,
    compute_map_usage,
    compute_scheduled_summary,
    compute_peak_heatmap,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/statistics", tags=["statistics"])


async def _get_all_missions():
    """Import and call mission listing from main module."""
    from app.main import list_missions_from_orion, list_scheduled_missions_from_orion
    regular = await list_missions_from_orion()
    scheduled = await list_scheduled_missions_from_orion()
    return regular, scheduled


@router.get("/missions/summary")
async def missions_summary(_user: UserResponse = Depends(get_current_user)):
    regular, scheduled = await _get_all_missions()
    return compute_mission_summary(regular)


@router.get("/missions/over-time")
async def missions_over_time(
    period: str = Query("day", pattern="^(day|week|month|year)$"),
    _user: UserResponse = Depends(get_current_user),
):
    regular, _ = await _get_all_missions()
    return compute_missions_over_time(regular, period)


@router.get("/missions/duration")
async def missions_duration(_user: UserResponse = Depends(get_current_user)):
    regular, _ = await _get_all_missions()
    return compute_duration_stats(regular)


@router.get("/robots/utilization")
async def robots_utilization(_user: UserResponse = Depends(get_current_user)):
    regular, _ = await _get_all_missions()
    return compute_robot_utilization(regular)


@router.get("/missions/status-distribution")
async def status_distribution(_user: UserResponse = Depends(get_current_user)):
    regular, _ = await _get_all_missions()
    return compute_status_distribution(regular)


@router.get("/missions/peak-hours")
async def peak_hours(_user: UserResponse = Depends(get_current_user)):
    regular, _ = await _get_all_missions()
    return compute_peak_hours(regular)


@router.get("/overview")
async def overview(_user: UserResponse = Depends(get_current_user)):
    """Combined dashboard data in single request."""
    regular, scheduled = await _get_all_missions()
    return {
        "summary": compute_mission_summary(regular),
        "duration": compute_duration_stats(regular),
        "statusDistribution": compute_status_distribution(regular),
        "robotUtilization": compute_robot_utilization(regular),
        "peakHours": compute_peak_hours(regular),
        "missionTypeBreakdown": compute_mission_type_breakdown(regular, scheduled),
        "mapUsage": compute_map_usage(regular),
        "scheduledSummary": compute_scheduled_summary(scheduled),
        "peakHeatmap": compute_peak_heatmap(regular),
    }
