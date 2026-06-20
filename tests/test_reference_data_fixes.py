from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import cruise_email_dashboard.database.db as db_module
from cruise_email_dashboard.database.models import Base, User


class ReferenceDataFixesTests(unittest.TestCase):
    def test_init_db_does_not_create_legacy_staff_accounts(self) -> None:
        original_engine = db_module.engine
        original_session_local = db_module.SessionLocal
        original_database_url = db_module.DATABASE_URL

        repo_tmp_root = Path(__file__).resolve().parents[1] / "tmp_test_reference_data"
        repo_tmp_root.mkdir(parents=True, exist_ok=True)
        tmpdir = repo_tmp_root / f"case_{uuid.uuid4().hex}"
        tmpdir.mkdir(parents=True, exist_ok=True)
        try:
            temp_db_path = tmpdir / "reference-data-test.db"
            temp_engine = create_engine(f"sqlite:///{temp_db_path.as_posix()}", future=True, connect_args={"check_same_thread": False})
            temp_session_local = sessionmaker(
                bind=temp_engine,
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
            )
            db_module.engine = temp_engine
            db_module.SessionLocal = temp_session_local
            db_module.DATABASE_URL = f"sqlite:///{temp_db_path.as_posix()}"

            try:
                Base.metadata.create_all(bind=temp_engine)
                db_module._run_reference_data_fixes()

                with db_module.session_scope() as db:
                    usernames = {row.username for row in db.query(User).all()}

                self.assertEqual(usernames, set())
            finally:
                temp_engine.dispose()
                db_module.engine = original_engine
                db_module.SessionLocal = original_session_local
                db_module.DATABASE_URL = original_database_url
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
