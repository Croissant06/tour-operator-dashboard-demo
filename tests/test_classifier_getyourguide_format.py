from cruise_email_dashboard.database.db import SessionLocal
from cruise_email_dashboard.database.models import EmailStatus
from cruise_email_dashboard.services.classifier import classify_email


def test_getyourguide_style_blocks_keep_demo_city_logic():
    body = """
GetYourGuide booking notification

Destination
Bay Harbor

Customer
Jordan Vale

Booking reference
GYGDEMO123

Hotel
CI Bootstrap Hotel

Tour date
2026-07-08

Adults
2
""".strip()

    with SessionLocal() as db:
        result = classify_email(
            db,
            subject="GetYourGuide booking notification - Bay Harbor",
            body=body,
            fallback_sender="notifications@reply.getyourguide.com",
        )

    assert result.customer_name == "Jordan Vale"
    assert result.booking_number == "GYGDEMO123"
    assert result.external_ref == "GYGDEMO123"
    assert result.raw_hotel_extraction == "CI Bootstrap Hotel"
    assert result.extraction_source == "getyourguide_format"
    assert result.detected_city_name == "Bay Harbor"
    assert result.booking_type == "BAY_HARBOR"
    assert result.num_adults == 2
    assert result.matched_hotel is not None
    assert result.matched_hotel.name == "CI Bootstrap Hotel"
    assert result.matched_bus_stop is not None
    assert result.matched_bus_stop.name == "Harbor Pier Stop"
    assert result.resolved_status == EmailStatus.pending
