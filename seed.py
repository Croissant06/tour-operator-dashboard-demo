from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from cruise_email_dashboard.database.db import Base, engine, init_db, session_scope
from cruise_email_dashboard.database.models import BusStop, City, EmailLog, EmailStatus, Hotel, Schedule, User, UserRole, VehicleType
from cruise_email_dashboard.services.auth import hash_password
from cruise_email_dashboard.services.reply_generator import MISSING_PICKUP_TIME_PLACEHOLDER, regenerate_email_draft
from cruise_email_dashboard.services.scheduler import resolve_pickup_schedule


CITY_DATA = {
    "Bay Harbor": {
        "aliases": "bay harbor,harbor bay",
        "stops": [
            ("Harbor Pier Stop", "Harbor Pier, Bay Harbor", 36.6101, -121.8912, "the curbside stop beside the main harbor pier", "08:30"),
            ("Marina Walk Stop", "Marina Walk, Bay Harbor", 36.6123, -121.8874, "the passenger loading area by Marina Walk", "08:40"),
            ("Sunset Boulevard Stop", "Sunset Boulevard, Bay Harbor", 36.6078, -121.8841, "the marked shuttle stop on Sunset Boulevard", "08:50"),
            ("Seaside Market Stop", "Seaside Market, Bay Harbor", 36.6049, -121.8798, "the pickup bay outside Seaside Market", "09:00"),
            ("Lighthouse Point Stop", "Lighthouse Point, Bay Harbor", 36.6162, -121.8954, "the roadside stop below Lighthouse Point", "09:10"),
        ],
        "hotels": [
            ("Bay Harbor Resort", "Harbor Resort,Bay Resort", "Harbor Pier Stop"),
            ("Marina View Hotel", "Marina View", "Marina Walk Stop"),
            ("Sunset Sands Lodge", "Sunset Sands", "Sunset Boulevard Stop"),
            ("Seaside Garden Suites", "Seaside Garden", "Seaside Market Stop"),
            ("Lighthouse Point Hotel", "Lighthouse Hotel", "Lighthouse Point Stop"),
        ],
    },
    "Coral Cove": {
        "aliases": "coral cove,cove",
        "stops": [
            ("Coral Plaza Stop", "Coral Plaza, Coral Cove", 36.5904, -121.8615, "the shuttle bay at Coral Plaza", "09:20"),
            ("Reefside Market Stop", "Reefside Market, Coral Cove", 36.5876, -121.8562, "the signed pickup bay beside Reefside Market", "09:30"),
            ("Lagoon Avenue Stop", "Lagoon Avenue, Coral Cove", 36.5843, -121.8521, "the sheltered stop on Lagoon Avenue", "09:40"),
            ("Cove Boardwalk Stop", "Cove Boardwalk, Coral Cove", 36.5818, -121.8487, "the passenger zone at the Cove Boardwalk entrance", "09:50"),
            ("Tidepool Gardens Stop", "Tidepool Gardens, Coral Cove", 36.5799, -121.8455, "the loading area outside Tidepool Gardens", "10:00"),
        ],
        "hotels": [
            ("Coral Cove Inn", "Cove Inn", "Coral Plaza Stop"),
            ("Reefside Retreat", "Reefside", "Reefside Market Stop"),
            ("Lagoon Blue Hotel", "Lagoon Blue", "Lagoon Avenue Stop"),
            ("Boardwalk Harbor House", "Boardwalk House", "Cove Boardwalk Stop"),
            ("Tidepool Garden Villas", "Tidepool Villas", "Tidepool Gardens Stop"),
        ],
    },
}


SAMPLE_EMAILS = [
    {
        "subject": "Bay Harbor Booking Confirmation",
        "sender_email": "amelia.stone@example.test",
        "sender_name": "Amelia Stone",
        "hotel_name": "Bay Harbor Resort",
        "booking_type": "BAY_HARBOR",
        "cruise_date": date(2026, 7, 8),
        "cruise_time": time(9, 30),
        "num_adults": 2,
        "booking_number": "RTD-BH-1001",
        "total_price": "180 EUR",
        "customer_phone": "+15550100101",
        "language": "en",
        "status": EmailStatus.pending,
    },
    {
        "subject": "Coral Cove Booking Confirmation",
        "sender_email": "marco.rivera@example.test",
        "sender_name": "Marco Rivera",
        "hotel_name": "Coral Cove Inn",
        "booking_type": "CORAL_COVE",
        "cruise_date": date(2026, 7, 9),
        "cruise_time": time(10, 30),
        "num_adults": 4,
        "booking_number": "RTD-CC-2001",
        "total_price": "320 EUR",
        "customer_phone": "+15550100202",
        "language": "en",
        "status": EmailStatus.sent,
    },
    {
        "subject": "Bay Harbor Family Booking",
        "sender_email": "nora.ellis@example.test",
        "sender_name": "Nora Ellis",
        "hotel_name": "Sunset Sands Lodge",
        "booking_type": "BAY_HARBOR",
        "cruise_date": date(2026, 7, 10),
        "cruise_time": time(9, 30),
        "num_adults": 3,
        "booking_number": "RTD-BH-1002",
        "total_price": "270 EUR",
        "customer_phone": "+15550100303",
        "language": "en",
        "status": EmailStatus.pending,
    },
    {
        "subject": "Coral Cove Shuttle Details Needed",
        "sender_email": "liam.chen@example.test",
        "sender_name": "Liam Chen",
        "hotel_name": "Unknown Guest House",
        "booking_type": "CORAL_COVE",
        "cruise_date": date(2026, 7, 11),
        "cruise_time": time(10, 30),
        "num_adults": 2,
        "booking_number": "RTD-CC-2002",
        "total_price": "160 EUR",
        "customer_phone": "+15550100404",
        "language": "en",
        "status": EmailStatus.manual,
    },
    {
        "subject": "Bay Harbor Group Booking",
        "sender_email": "sofia.bennett@example.test",
        "sender_name": "Sofia Bennett",
        "hotel_name": "Marina View Hotel",
        "booking_type": "BAY_HARBOR",
        "cruise_date": date(2026, 7, 12),
        "cruise_time": time(9, 30),
        "num_adults": 5,
        "booking_number": "RTD-BH-1003",
        "total_price": "450 EUR",
        "customer_phone": "+15550100505",
        "language": "en",
        "status": EmailStatus.pending,
    },
]


def seed() -> None:
    Base.metadata.drop_all(bind=engine)
    init_db()

    with session_scope() as db:
        stops_by_name: dict[str, BusStop] = {}
        hotels_by_name: dict[str, Hotel] = {}

        for city_name, city_data in CITY_DATA.items():
            city = City(name=city_name, local_name=city_name, timezone="UTC", aliases=city_data["aliases"])
            db.add(city)
            db.flush()

            for stop_name, address, lat, lng, description, pickup in city_data["stops"]:
                stop = BusStop(
                    name=stop_name,
                    address=address,
                    latitude=lat,
                    longitude=lng,
                    city_id=city.id,
                    maps_url=f"https://maps.example.test/?q={lat},{lng}",
                    description=description,
                    vehicle_type=VehicleType.shuttle,
                )
                db.add(stop)
                db.flush()
                stops_by_name[stop_name] = stop
                db.add(Schedule(bus_stop_id=stop.id, pickup_time=time.fromisoformat(pickup), season_label="default"))

            for hotel_name, aliases, stop_name in city_data["hotels"]:
                hotel = Hotel(
                    name=hotel_name,
                    aliases=aliases,
                    bus_stop_id=stops_by_name[stop_name].id,
                    city_id=city.id,
                )
                db.add(hotel)
                db.flush()
                hotels_by_name[hotel_name] = hotel

        db.add_all(
            [
                User(username="demo_admin", hashed_password=hash_password("demo123"), role=UserRole.admin),
                User(username="demo_staff", hashed_password=hash_password("demo123"), role=UserRole.staff),
            ]
        )
        db.flush()

        for index, item in enumerate(SAMPLE_EMAILS, start=1):
            detected_hotel = hotels_by_name.get(item["hotel_name"])
            bus_stop = detected_hotel.bus_stop if detected_hotel else None
            email = EmailLog(
                message_id=f"<{item['booking_number']}@rivieratoursdemo.local>",
                received_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=index * 3),
                sender_email=item["sender_email"],
                sender_name=item["sender_name"],
                subject=item["subject"],
                body_snippet=f"Demo booking for {item['sender_name']}",
                full_body=f"Demo booking email for {item['sender_name']} staying at {item['hotel_name']}.",
                detected_language=item["language"],
                template_language=item["language"],
                detected_hotel_id=detected_hotel.id if detected_hotel else None,
                assigned_bus_stop_id=bus_stop.id if bus_stop else None,
                booking_type=item["booking_type"],
                cruise_date=item["cruise_date"],
                cruise_time=item["cruise_time"],
                num_adults=item["num_adults"],
                num_children=0,
                customer_phone=item["customer_phone"],
                booking_number=item["booking_number"],
                external_ref="",
                total_price=item["total_price"],
                detected_city=item["booking_type"].replace("_", " ").title(),
                raw_customer_name_extraction=item["sender_name"],
                raw_hotel_extraction=item["hotel_name"],
                extraction_source="demo_seed",
                status=item["status"],
                is_new=item["status"] != EmailStatus.sent,
                warning_note="" if detected_hotel else "Hotel name not found in booking - manual assignment required.",
                sent_at=(datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=index * 3 - 1)) if item["status"] == EmailStatus.sent else None,
            )
            if bus_stop:
                email.detected_hotel = detected_hotel
                email.assigned_bus_stop = bus_stop
                resolution = resolve_pickup_schedule(db, bus_stop, email.booking_type, email.cruise_date)
                email.pickup_time_text = resolution.schedule.pickup_time.strftime("%H:%M") if resolution.schedule else MISSING_PICKUP_TIME_PLACEHOLDER
                regenerate_email_draft(email)
            db.add(email)

    print("Seed complete. Demo users: demo_admin/demo123 and demo_staff/demo123")


if __name__ == "__main__":
    seed()
