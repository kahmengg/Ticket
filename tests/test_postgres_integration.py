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
from alembic import command
from alembic.config import Config
from sqlalchemy import text, inspect
# Exercise the populated upgrade, not just fresh schema creation.
command.upgrade(Config("alembic.ini"), "20260908_0004")
with engine.begin() as conn:
    conn.execute(text("INSERT INTO events (id,title,url,status,content_hash,first_seen_at,last_seen_at,created_at,updated_at) VALUES (9001,'ARTIST: Tour','https://example.com','active','old',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    conn.execute(text("INSERT INTO alerts (event_id,chat_id,alert_type,message,created_at) VALUES (9001,'123','new_event','retained',CURRENT_TIMESTAMP)"))
init_db()
init_db()
with engine.connect() as conn:
    assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "20260910_0005"
    assert conn.execute(text("SELECT discovery_kind, discovered_at, sort_title FROM events WHERE id=9001")).one() == ('legacy', None, 'artist tour')
    assert conn.scalar(text("SELECT message FROM alerts WHERE event_id=9001")) == 'retained'
    assert 'ix_events_browse_discovery' in {i['name'] for i in inspect(conn).get_indexes('events')}
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
