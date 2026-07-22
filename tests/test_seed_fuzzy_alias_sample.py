from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_seed_includes_alias_booking_matched_through_classifier(tmp_path: Path) -> None:
    db_path = tmp_path / "seed-alias.db"
    env = {
        **os.environ,
        "IMAP_HOST": "mail.example.test",
        "IMAP_USER": "demo@example.test",
        "IMAP_PASSWORD": "demo",
        "SMTP_HOST": "mail.example.test",
        "SMTP_USER": "demo@example.test",
        "SMTP_PASSWORD": "demo",
        "SECRET_KEY": "test-secret",
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
    }

    result = subprocess.run(
        [sys.executable, "seed.py"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    con = sqlite3.connect(db_path)
    try:
        assert con.execute("SELECT COUNT(*) FROM emails_log").fetchone()[0] == 6
        row = con.execute(
            """
            SELECT e.raw_hotel_extraction, e.extraction_source, h.name, b.name, e.pickup_time_text, e.draft_reply
            FROM emails_log e
            LEFT JOIN hotels h ON h.id = e.detected_hotel_id
            LEFT JOIN bus_stops b ON b.id = e.assigned_bus_stop_id
            WHERE e.subject = 'Bay Harbor Alias Booking'
            """
        ).fetchone()
    finally:
        con.close()

    assert row is not None
    raw_hotel, extraction_source, hotel_name, stop_name, pickup_time, draft_reply = row
    assert raw_hotel == "Harbor Resort"
    assert extraction_source == "booking_fields"
    assert hotel_name == "Bay Harbor Resort"
    assert stop_name == "Harbor Pier Stop"
    assert pickup_time == "08:30"
    assert "Pickup point: Harbor Pier Stop" in draft_reply
