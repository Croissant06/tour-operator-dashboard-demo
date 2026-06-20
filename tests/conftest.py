from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

from cruise_email_dashboard.database.db import DATABASE_URL, SessionLocal, init_db
from cruise_email_dashboard.database.models import BusStop, City, EmailLog, EmailStatus, Hotel, Schedule, User, UserRole, VehicleType
from cruise_email_dashboard.services.auth import hash_password


def _sqlite_path() -> Path | None:
    if not DATABASE_URL.startswith("sqlite:///"):
        return None
    raw_path = DATABASE_URL.removeprefix("sqlite:///")
    return Path(raw_path)


def _reset_ci_sqlite_db() -> None:
    db_path = _sqlite_path()
    if db_path is None:
        return
    if "ci-test" not in db_path.name:
        return
    if db_path.exists():
        db_path.unlink()


def _ensure_user(db, username: str, password: str, role: UserRole) -> None:
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        existing.hashed_password = hash_password(password)
        existing.role = role
        return
    db.add(User(username=username, hashed_password=hash_password(password), role=role))


def _ensure_city(db, name: str) -> City:
    city = db.query(City).filter(City.name == name).first()
    if city:
        return city
    city = City(name=name, local_name=name, timezone="UTC", aliases=name.lower())
    db.add(city)
    db.flush()
    return city


def _ensure_stop(
    db,
    *,
    city_id: int,
    name: str,
    address: str,
    latitude: float,
    longitude: float,
    description: str,
) -> BusStop:
    stop = db.query(BusStop).filter(BusStop.name == name).first()
    if stop:
        stop.city_id = city_id
        stop.address = address
        stop.latitude = latitude
        stop.longitude = longitude
        stop.description = description
        stop.maps_url = f"https://maps.example.test/?q={latitude},{longitude}"
        stop.vehicle_type = VehicleType.shuttle
        return stop
    stop = BusStop(
        name=name,
        address=address,
        latitude=latitude,
        longitude=longitude,
        city_id=city_id,
        maps_url=f"https://maps.example.test/?q={latitude},{longitude}",
        description=description,
        vehicle_type=VehicleType.shuttle,
    )
    db.add(stop)
    db.flush()
    db.add(Schedule(bus_stop_id=stop.id, pickup_time=time(8, 30), season_label="default"))
    db.flush()
    return stop


def _ensure_hotel(db, *, city_id: int, bus_stop_id: int, name: str, aliases: str) -> Hotel:
    hotel = db.query(Hotel).filter(Hotel.name == name).first()
    if hotel:
        hotel.city_id = city_id
        hotel.bus_stop_id = bus_stop_id
        hotel.aliases = aliases
        return hotel
    hotel = Hotel(name=name, aliases=aliases, city_id=city_id, bus_stop_id=bus_stop_id)
    db.add(hotel)
    db.flush()
    return hotel


def _ensure_email(db, *, hotel: Hotel, stop: BusStop) -> None:
    existing = db.query(EmailLog).filter(EmailLog.message_id == "<ci-bootstrap-email@rivieratoursdemo.local>").first()
    if existing:
        return
    db.add(
        EmailLog(
            message_id="<ci-bootstrap-email@rivieratoursdemo.local>",
            received_at=datetime(2026, 6, 18, 10, 0, 0),
            sender_email="customer@example.com",
            sender_name="CI Test Guest",
            subject="Bay Harbor Booking Confirmation",
            body_snippet="CI bootstrap booking",
            full_body="CI bootstrap booking body",
            detected_language="en",
            template_language="en",
            detected_hotel_id=hotel.id,
            assigned_bus_stop_id=stop.id,
            booking_type="BAY_HARBOR",
            cruise_date=date(2026, 6, 19),
            cruise_time=time(9, 0),
            num_adults=2,
            num_children=0,
            customer_phone="+15550000000",
            booking_number="CI-BOOTSTRAP-1",
            external_ref="",
            total_price="100 EUR",
            detected_city="Bay Harbor",
            raw_customer_name_extraction="CI Test Guest",
            raw_hotel_extraction=hotel.name,
            extraction_source="ci_bootstrap",
            pickup_time_text="08:30",
            draft_reply="CI bootstrap draft",
            status=EmailStatus.pending,
            warning_note="",
            is_new=True,
        )
    )


def pytest_sessionstart(session) -> None:
    _reset_ci_sqlite_db()
    init_db()

    with SessionLocal() as db:
        _ensure_user(db, "demo_admin", "demo123", UserRole.admin)
        _ensure_user(db, "demo_staff", "demo123", UserRole.staff)

        bay_harbor = _ensure_city(db, "Bay Harbor")
        harbor_pier = _ensure_stop(
            db,
            city_id=bay_harbor.id,
            name="Harbor Pier Stop",
            address="Harbor Pier, Bay Harbor",
            latitude=36.6101,
            longitude=-121.8912,
            description="the curbside stop beside the main harbor pier",
        )
        marina_walk = _ensure_stop(
            db,
            city_id=bay_harbor.id,
            name="Marina Walk Stop",
            address="Marina Walk, Bay Harbor",
            latitude=36.6123,
            longitude=-121.8874,
            description="the passenger loading area by Marina Walk",
        )
        hotel = _ensure_hotel(
            db,
            city_id=bay_harbor.id,
            bus_stop_id=harbor_pier.id,
            name="CI Bootstrap Hotel",
            aliases="CI Hotel,Bootstrap Hotel",
        )
        _ensure_hotel(
            db,
            city_id=bay_harbor.id,
            bus_stop_id=marina_walk.id,
            name="Codex HM Test Existing",
            aliases="Existing Alias",
        )
        _ensure_email(db, hotel=hotel, stop=harbor_pier)
        db.commit()
