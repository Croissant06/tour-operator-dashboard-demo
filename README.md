# Riviera Tours Demo Dashboard

Sanitized demo dashboard for tour operators who need to process booking emails, match guests to pickup stops, and prepare staff-reviewed replies.

## What It Does

This demo app shows a fictional coastal tour operation with two towns, Bay Harbor and Coral Cove. It reads booking-style messages, matches guests to fictional hotels and pickup stops, and generates draft pickup replies for staff to review.

The dashboard also includes hotel management, pickup stop management, schedules, inbox history, and demo booking generation.

## Tech Stack

- FastAPI
- SQLAlchemy
- SQLite
- Jinja2
- Tailwind CSS
- APScheduler
- IMAP / SMTP integrations

## Demo Accounts

- Admin: `demo_admin` / `demo123`
- Staff: `demo_staff` / `demo123`

## Notes

- All cities, hotels, stops, customers, and booking examples are fictional.
- This repository is prepared for demos and does not include production deployment configuration.
