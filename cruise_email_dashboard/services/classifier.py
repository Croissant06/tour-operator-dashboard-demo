from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
import re
from email.utils import parseaddr

from bs4 import BeautifulSoup
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from cruise_email_dashboard.database.models import BusStop, City, EmailStatus, Hotel
from cruise_email_dashboard.services.reply_generator import HOTEL_REQUEST_WARNING

BOOKING_TYPE_BY_CITY = {
    "Bay Harbor": "BAY_HARBOR",
    "Coral Cove": "CORAL_COVE",
}

KNOWN_BOOKING_LABELS = {
    "accommodation",
    "adults",
    "booking number",
    "booking reference",
    "children",
    "customer",
    "customer name",
    "date",
    "destination",
    "guest",
    "guests",
    "hotel",
    "hotel name",
    "phone",
    "price",
    "reference",
    "time",
    "total price",
    "tour date",
    "tour time",
}


@dataclass
class ParsedBooking:
    notes_block: str = ""
    customer_name: str = ""
    customer_email: str = ""
    language: str = "en"
    booking_type: str = ""
    city_name: str = ""
    cruise_date: date | None = None
    cruise_time: time | None = None
    num_adults: int | None = None
    num_children: int | None = None
    customer_phone: str = ""
    booking_number: str = ""
    external_ref: str = ""
    total_price: str = ""
    raw_customer_name_extraction: str = ""
    raw_hotel_extraction: str = ""
    extraction_source: str = ""
    bus_stop_field: str = ""


@dataclass
class ClassificationResult:
    customer_name: str
    customer_email: str
    language: str
    booking_type: str
    cruise_date: date | None
    cruise_time: time | None
    num_adults: int | None
    num_children: int | None
    customer_phone: str
    booking_number: str
    external_ref: str
    total_price: str
    detected_city_name: str
    raw_customer_name_extraction: str
    raw_hotel_extraction: str
    extraction_source: str
    warning_note: str
    resolved_status: EmailStatus
    matched_hotel: Hotel | None
    matched_bus_stop: BusStop | None
    is_bus_request: bool
    selected_stop_time_text: str = ""


def _plain_text(html_body: str) -> str:
    return BeautifulSoup(html_body or "", "html.parser").get_text("\n", strip=True) if html_body else ""


def _normalize(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


def _field_value(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else ""


def _compact_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _is_getyourguide_format(subject: str, body: str, fallback_sender: str = "") -> bool:
    return "getyourguide" in f"{subject}\n{body}\n{fallback_sender}".lower()


def _build_label_map(html_body: str, text_body: str = "") -> dict[str, str]:
    source = "\n".join(part for part in [text_body, _plain_text(html_body)] if part)
    labels: dict[str, str] = {}
    lines = _compact_lines(source)
    for line in lines:
        if ":" not in line:
            continue
        label, value = line.split(":", 1)
        cleaned_label = _normalize(label)
        cleaned_value = value.strip()
        if cleaned_label and cleaned_value:
            labels[cleaned_label] = cleaned_value
    for index, line in enumerate(lines[:-1]):
        cleaned_label = _normalize(line)
        next_value = lines[index + 1].strip()
        if cleaned_label in KNOWN_BOOKING_LABELS and _normalize(next_value) not in KNOWN_BOOKING_LABELS:
            labels.setdefault(cleaned_label, next_value)
    return labels


def _parse_date(value: str) -> date | None:
    cleaned = value.strip()
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def _parse_time(value: str) -> time | None:
    cleaned = value.strip()
    for fmt in ("%H:%M", "%I:%M %p", "%I %p"):
        try:
            return datetime.strptime(cleaned, fmt).time()
        except ValueError:
            continue
    return None


def _detect_city(db: Session, subject: str, body: str) -> City | None:
    haystack = _normalize(f"{subject}\n{body}")
    for city in db.query(City).order_by(City.name.asc()).all():
        candidates = [city.name, *[alias.strip() for alias in (city.aliases or "").split(",") if alias.strip()]]
        if any(_normalize(candidate) in haystack for candidate in candidates):
            return city
    return db.query(City).order_by(City.name.asc()).first()


def _hotel_candidates(hotel: Hotel) -> list[str]:
    return [hotel.name, *[alias.strip() for alias in (hotel.aliases or "").split(",") if alias.strip()]]


def _find_hotel(db: Session, raw_hotel: str, city: City | None, threshold: int) -> Hotel | None:
    if not raw_hotel:
        return None
    query = db.query(Hotel)
    if city:
        query = query.filter(Hotel.city_id == city.id)
    hotels = query.all()
    raw_normalized = _normalize(raw_hotel)
    best_hotel: Hotel | None = None
    best_score = 0.0
    for hotel in hotels:
        for candidate in _hotel_candidates(hotel):
            candidate_normalized = _normalize(candidate)
            if not candidate_normalized:
                continue
            if candidate_normalized == raw_normalized:
                return hotel
            score = fuzz.token_set_ratio(raw_normalized, candidate_normalized)
            if score > best_score:
                best_score = score
                best_hotel = hotel
    return best_hotel if best_hotel and best_score >= threshold else None


def _infer_hotel_from_text(db: Session, subject: str, body: str, city: City | None) -> str:
    haystack = _normalize(f"{subject}\n{body}")
    query = db.query(Hotel)
    if city:
        query = query.filter(Hotel.city_id == city.id)
    for hotel in query.order_by(Hotel.name.asc()).all():
        for candidate in _hotel_candidates(hotel):
            normalized = _normalize(candidate)
            if normalized and normalized in haystack:
                return hotel.name
    return ""


def parse_booking_email(
    subject: str,
    text_body: str,
    html_body: str = "",
    fallback_sender: str = "",
    fallback_name: str = "",
) -> ParsedBooking:
    body = "\n".join(part for part in [text_body or "", _plain_text(html_body)] if part)
    label_map = _build_label_map(html_body, body)
    is_getyourguide_format = _is_getyourguide_format(subject, body, fallback_sender)
    sender_name, sender_email = parseaddr(fallback_sender or "")
    customer_name = (
        label_map.get("customer")
        or label_map.get("customer name")
        or label_map.get("guest")
        or fallback_name
        or sender_name
        or "Guest"
    )
    raw_hotel = (
        label_map.get("hotel")
        or label_map.get("hotel name")
        or label_map.get("accommodation")
        or _field_value(r"^(?:hotel|accommodation)\s*[:\-]\s*(.+)$", body)
    )
    booking_number = (
        label_map.get("booking number")
        or label_map.get("booking reference")
        or label_map.get("reference")
        or _field_value(r"^(?:booking number|booking reference|reference)\s*[:\-]\s*([A-Z0-9\-]+)$", body)
    )
    external_ref = booking_number
    if is_getyourguide_format and not external_ref:
        external_ref = _field_value(r"\b(GYG[A-Z0-9\-]+)\b", body)
    cruise_date = _parse_date(
        label_map.get("date", "")
        or label_map.get("tour date", "")
        or _field_value(r"^(?:date|tour date)\s*[:\-]\s*(.+)$", body)
    )
    cruise_time = _parse_time(
        label_map.get("time", "")
        or label_map.get("tour time", "")
        or _field_value(r"^(?:time|tour time)\s*[:\-]\s*(.+)$", body)
    )
    adults_text = label_map.get("adults", "") or _field_value(r"^(?:adults|guests)\s*[:\-]\s*(\d+)", body)
    children_text = label_map.get("children", "") or _field_value(r"^children\s*[:\-]\s*(\d+)", body)
    total_price = label_map.get("total price") or label_map.get("price") or ""
    return ParsedBooking(
        notes_block=body,
        customer_name=customer_name,
        customer_email=sender_email or fallback_sender,
        cruise_date=cruise_date,
        cruise_time=cruise_time,
        num_adults=int(adults_text) if adults_text.isdigit() else None,
        num_children=int(children_text) if children_text.isdigit() else None,
        customer_phone=label_map.get("phone", ""),
        booking_number=booking_number,
        external_ref=external_ref,
        total_price=total_price,
        raw_customer_name_extraction=customer_name,
        raw_hotel_extraction=raw_hotel,
        extraction_source="getyourguide_format" if raw_hotel and is_getyourguide_format else "booking_fields" if raw_hotel else "",
    )


def classify_email(
    db: Session,
    *,
    subject: str,
    body: str,
    threshold: int = 80,
    html_body: str = "",
    fallback_sender: str = "",
    fallback_name: str = "",
) -> ClassificationResult:
    parsed = parse_booking_email(subject, body, html_body, fallback_sender, fallback_name)
    body_text = "\n".join(part for part in [body or "", _plain_text(html_body)] if part)
    city = _detect_city(db, subject, body_text)
    raw_hotel = parsed.raw_hotel_extraction or _infer_hotel_from_text(db, subject, body_text, city)
    matched_hotel = _find_hotel(db, raw_hotel, city, threshold)
    matched_bus_stop = matched_hotel.bus_stop if matched_hotel else None
    detected_city_name = city.name if city else ""
    booking_type = BOOKING_TYPE_BY_CITY.get(detected_city_name, parsed.booking_type)
    cancelled = "cancel" in _normalize(subject)
    warning_note = ""
    status = EmailStatus.pending
    is_bus_request = True

    if cancelled:
        status = EmailStatus.cancelled
        is_bus_request = False
    elif not raw_hotel:
        warning_note = HOTEL_REQUEST_WARNING
    elif not matched_hotel:
        warning_note = "No hotel match found above the configured fuzzy threshold."

    return ClassificationResult(
        customer_name=parsed.customer_name,
        customer_email=parsed.customer_email,
        language="en",
        booking_type=booking_type or "",
        cruise_date=parsed.cruise_date,
        cruise_time=parsed.cruise_time,
        num_adults=parsed.num_adults,
        num_children=parsed.num_children,
        customer_phone=parsed.customer_phone,
        booking_number=parsed.booking_number,
        external_ref=parsed.external_ref,
        total_price=parsed.total_price,
        detected_city_name=detected_city_name,
        raw_customer_name_extraction=parsed.raw_customer_name_extraction,
        raw_hotel_extraction=raw_hotel,
        extraction_source=parsed.extraction_source or ("hotel_name_match" if raw_hotel else ""),
        warning_note=warning_note,
        resolved_status=status,
        matched_hotel=matched_hotel,
        matched_bus_stop=matched_bus_stop,
        is_bus_request=is_bus_request,
    )
