from __future__ import annotations

import re
import unittest

from fastapi.testclient import TestClient

from cruise_email_dashboard.database.db import SessionLocal
from cruise_email_dashboard.database.models import EmailLog
from cruise_email_dashboard.main import app
from tests.test_helpers import login_with_csrf


class InboxRowActionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app, base_url="https://testserver")
        login_with_csrf(self.client, "demo_staff", "demo123")

    def test_mark_unread_control_cannot_trigger_parent_row_navigation(self) -> None:
        with SessionLocal() as db:
            email = db.query(EmailLog).order_by(EmailLog.id.asc()).first()
            self.assertIsNotNone(email)
            email.is_new = False
            db.commit()
            email_id = email.id

        response = self.client.get("/inbox?quick_range=all")

        self.assertEqual(response.status_code, 200)
        row_match = re.search(rf'<tr id="email-row-{email_id}"[^>]*onclick="([^"]+)"', response.text)
        self.assertIsNotNone(row_match)
        self.assertIn("closest", row_match.group(1))
        self.assertIn("button", row_match.group(1))
        self.assertIn(f'data-mark-unread-id="{email_id}"', response.text)
        self.assertIn("event.stopPropagation();", response.text)


if __name__ == "__main__":
    unittest.main()
