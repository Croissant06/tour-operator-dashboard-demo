from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import logging

from sqlalchemy.orm import Session

from cruise_email_dashboard.database.models import BusStop, Schedule

logger = logging.getLogger(__name__)


@dataclass
class ScheduleResolution:
    schedule: Schedule | None
    warning_note: str = ""


def _day_matches(schedule: Schedule, cruise_date: date | None) -> bool:
    if not schedule.valid_days or not cruise_date:
        return True
    allowed_days = {part.strip() for part in schedule.valid_days.split(",") if part.strip()}
    return str(cruise_date.weekday()) in allowed_days


def resolve_pickup_schedule(
    db: Session,
    bus_stop: BusStop | None,
    booking_type: str = "",
    cruise_date: date | None = None,
) -> ScheduleResolution:
    if not bus_stop:
        return ScheduleResolution(schedule=None)

    target_date = cruise_date or date.today()
    schedules = db.query(Schedule).filter(Schedule.bus_stop_id == bus_stop.id).order_by(Schedule.pickup_time.asc()).all()

    default_matches: list[Schedule] = []
    eligible_matches: list[Schedule] = []
    for schedule in schedules:
        start_ok = schedule.valid_from is None or schedule.valid_from <= target_date
        end_ok = schedule.valid_to is None or schedule.valid_to >= target_date
        day_ok = _day_matches(schedule, target_date)
        if not (start_ok and end_ok and day_ok):
            continue
        if schedule.season_label == "default":
            default_matches.append(schedule)
        else:
            eligible_matches.append(schedule)

    if default_matches:
        return ScheduleResolution(schedule=default_matches[0])
    if eligible_matches:
        return ScheduleResolution(schedule=eligible_matches[0])

    warning_note = f"No schedule found for stop {bus_stop.name} - manual time entry required."
    logger.warning("[SCHEDULER] %s", warning_note)
    return ScheduleResolution(schedule=None, warning_note=warning_note)
