from __future__ import annotations

import unittest
from datetime import date, time

from cruise_email_dashboard.database.models import BusStop, City, EmailLog, Hotel, VehicleType
from cruise_email_dashboard.services.reply_generator import build_reply, regenerate_email_draft


def make_email(
    *,
    stop_name: str = "Harbor Pier Stop",
    stop_description: str = "the curbside stop beside the main harbor pier",
    city_name: str = "Bay Harbor",
    language: str = "en",
    pickup_time: str = "08:30",
    num_adults: int = 2,
    num_children: int = 0,
) -> EmailLog:
    city = City(name=city_name)
    stop = BusStop(
        name=stop_name,
        address=f"{stop_name}, {city_name}",
        latitude=36.0,
        longitude=-121.0,
        maps_url="https://maps.example.test/harbor-pier",
        description=stop_description,
        vehicle_type=VehicleType.shuttle,
    )
    stop.city = city
    hotel = Hotel(name="Bay Harbor Resort", aliases="Harbor Resort")
    hotel.bus_stop = stop
    hotel.bus_stop_id = 1

    email = EmailLog(
        received_at=date(2026, 6, 8),
        sender_email="guest@example.com",
        sender_name="Test Guest",
        subject="Booking Confirmation",
        full_body="Body",
        detected_language=language,
        template_language=language,
        booking_type=city_name.upper().replace(" ", "_"),
        cruise_date=date(2026, 6, 10),
        cruise_time=time(9, 0),
        num_adults=num_adults,
        num_children=num_children,
        pickup_time_text=pickup_time,
        raw_hotel_extraction=hotel.name,
    )
    email.assigned_bus_stop = stop
    email.assigned_bus_stop_id = 1
    email.detected_hotel = hotel
    email.detected_hotel_id = 1
    return email


class OfficialPickupCopyTests(unittest.TestCase):
    def test_generic_pickup_reply_uses_fictional_stop_description_and_signature(self) -> None:
        email = make_email()

        reply, _, _ = build_reply(email)

        self.assertIn("Dear Test Guest,", reply)
        self.assertIn(
            "Please find attached the pickup point you have selected. The pickup point is the curbside stop beside the main harbor pier. Our transport will be there at 08:30 to collect you.",
            reply,
        )
        self.assertIn("Kind Regards,\nRiviera Tours Demo", reply)

    def test_coral_cove_booking_label_is_generic(self) -> None:
        email = make_email(
            stop_name="Reefside Market Stop",
            stop_description="the signed pickup bay beside Reefside Market",
            city_name="Coral Cove",
            pickup_time="10:15",
        )

        reply, _, _ = build_reply(email)

        self.assertIn("Coral Cove", reply)
        self.assertIn("the signed pickup bay beside Reefside Market", reply)

    def test_participants_label_handles_adults_only(self) -> None:
        reply, _, _ = build_reply(make_email(num_adults=1, num_children=0))
        self.assertIn("for 1 adult.", reply)

        reply, _, _ = build_reply(make_email(num_adults=2, num_children=0))
        self.assertIn("for 2 adults.", reply)

    def test_participants_label_handles_one_child(self) -> None:
        reply, _, _ = build_reply(make_email(num_adults=2, num_children=1))

        self.assertIn("for 2 adults and 1 child.", reply)

    def test_participants_label_handles_multiple_children(self) -> None:
        reply, _, _ = build_reply(make_email(num_adults=2, num_children=2))

        self.assertIn("for 2 adults and 2 children.", reply)

    def test_unmatched_hotel_generates_english_clarification_draft(self) -> None:
        email = EmailLog(
            received_at=date(2026, 6, 8),
            sender_email="guest@example.com",
            sender_name="Test Guest",
            subject="Booking Confirmation",
            full_body="Body",
            detected_language="en",
            template_language="en",
            booking_type="BAY_HARBOR",
            cruise_date=date(2026, 6, 10),
            num_adults=2,
            raw_hotel_extraction="Unknown Lodge",
        )

        reply, _, _ = build_reply(email)

        self.assertIn("We were unable to identify your hotel from the booking details.", reply)
        self.assertIn("Could you please reply with the name of your hotel or accommodation", reply)
        self.assertIn("Riviera Tours Demo", reply)
        regenerate_email_draft(email)
        self.assertIn("We were unable to identify your hotel from the booking details.", email.draft_reply)


if __name__ == "__main__":
    unittest.main()
