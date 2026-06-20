from __future__ import annotations

from pathlib import Path
import re

from cruise_email_dashboard.database.models import EmailLog
from cruise_email_dashboard.services.official_pickup_copy import render_official_pickup_copy

REPLIES_DIR = Path(__file__).resolve().parents[1] / "templates" / "replies"
SUPPORTED_LANGUAGES = {"en"}
MISSING_PICKUP_TIME_PLACEHOLDER = "[PICKUP TIME NOT FOUND]"
HOTEL_REQUEST_WARNING = "No hotel provided by customer"
HOTEL_CLARIFICATION_VARIANT = "hotel_clarification"
PICKUP_VARIANT = "pickup"


def available_template_files() -> list[Path]:
    return sorted(path for path in REPLIES_DIR.glob("*.txt") if path.parent == REPLIES_DIR)


def _needs_hotel_clarification(email_log: EmailLog) -> bool:
    return not email_log.detected_hotel and not email_log.assigned_bus_stop


def _template_variant(email_log: EmailLog) -> str:
    if HOTEL_REQUEST_WARNING in (email_log.warning_note or ""):
        return "hotel_request"
    if _needs_hotel_clarification(email_log):
        return HOTEL_CLARIFICATION_VARIANT
    return PICKUP_VARIANT


def template_path(variant: str, language: str) -> Path:
    return REPLIES_DIR / f"{language}_{variant}.txt"


def load_template(variant: str, language: str) -> tuple[str, str, str]:
    requested = (language or "en").lower()
    fallback_note = ""
    if requested not in SUPPORTED_LANGUAGES or not template_path(variant, requested).exists():
        fallback_note = f"Template for '{variant}/{requested}' not found; fell back to English."
        requested = "en"
    return template_path(variant, requested).read_text(encoding="utf-8"), requested, fallback_note


def _booking_type_label(email_log: EmailLog) -> str:
    labels = {
        "BAY_HARBOR": "Bay Harbor",
        "CORAL_COVE": "Coral Cove",
    }
    if email_log.booking_type in labels:
        return labels[email_log.booking_type]
    stop = email_log.assigned_bus_stop
    if stop and stop.city:
        return stop.city.name
    return "Riviera Tours Demo"


def _pickup_instructions(email_log: EmailLog, language: str) -> str:
    stop = email_log.assigned_bus_stop
    if not stop:
        return ""
    pickup_time = email_log.pickup_time_text or MISSING_PICKUP_TIME_PLACEHOLDER
    official = render_official_pickup_copy(stop.name, language, pickup_time, email_log.cruise_time)
    if official:
        return official
    description = stop.description or stop.name
    return (
        "Please find attached the pickup point you have selected. "
        f"The pickup point is {description}. "
        f"Our transport will be there at {pickup_time} to collect you."
    )


def _format_context(email_log: EmailLog) -> dict[str, str]:
    stop = email_log.assigned_bus_stop
    hotel = email_log.detected_hotel
    cruise_date = email_log.cruise_date.strftime("%d %B %Y") if email_log.cruise_date else "your tour date"
    cruise_day = email_log.cruise_date.strftime("%A") if email_log.cruise_date else "scheduled day"
    language = (email_log.detected_language or "en").lower()
    return {
        "customer_name": email_log.sender_name or "Guest",
        "cruise_date": cruise_date,
        "cruise_day": cruise_day,
        "booking_type": _booking_type_label(email_log),
        "num_adults": str(email_log.num_adults or ""),
        "hotel_name": hotel.name if hotel else email_log.raw_hotel_extraction or "your hotel",
        "bus_stop_name": stop.name if stop else "",
        "bus_stop_address": stop.address if stop else "",
        "bus_stop_description": stop.description if stop and stop.description else (stop.name if stop else ""),
        "pickup_instructions": _pickup_instructions(email_log, language),
        "pickup_time": email_log.pickup_time_text or MISSING_PICKUP_TIME_PLACEHOLDER,
        "maps_url": stop.maps_url if stop and stop.maps_url else "",
        "company_name": "Riviera Tours Demo",
        "company_email": "bookings@rivieratoursdemo.example",
        "company_phone": "",
        "support_contact_info": "bookings@rivieratoursdemo.example",
    }


def _clean_rendered_reply(reply: str) -> str:
    cleaned = reply.replace("\r\n", "\n")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() + "\n"


def build_reply(email_log: EmailLog) -> tuple[str, str, str]:
    template, chosen_language, warning_note = load_template(_template_variant(email_log), email_log.detected_language)
    return _clean_rendered_reply(template.format(**_format_context(email_log))), chosen_language, warning_note


def regenerate_email_draft(email_log: EmailLog) -> None:
    stop = email_log.assigned_bus_stop
    variant = _template_variant(email_log)
    if not stop and variant not in {"hotel_request", HOTEL_CLARIFICATION_VARIANT}:
        email_log.draft_reply = ""
        return
    reply, template_language, warning_note = build_reply(email_log)
    email_log.draft_reply = reply
    email_log.template_language = template_language
    email_log.warning_note = "\n".join(part for part in [email_log.warning_note, warning_note] if part).strip()
