import os
import subprocess
import sys

import pytest
from sqlalchemy.engine import make_url


def test_postgres_migrations_and_exclusive_source_lock():
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Dedicated Postgres test database is not configured")
    parsed = make_url(url)
    # Never run integration migrations against a remote or production database.
    assert parsed.host in {"localhost", "127.0.0.1"} and parsed.database == "ticket_test"
    script = '''
from app.database import init_db, engine
from app.services.job_lock import source_check_lock
from sqlalchemy import text
init_db()
init_db()
with engine.connect() as conn:
    assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "20260908_0004"
with source_check_lock(engine) as first:
    assert first
    with source_check_lock(engine) as second:
        assert not second
with source_check_lock(engine) as released:
    assert released
'''
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                            env=dict(os.environ, DATABASE_URL=url, ENABLE_SCHEDULER="false"))
    assert result.returncode == 0, result.stderr
