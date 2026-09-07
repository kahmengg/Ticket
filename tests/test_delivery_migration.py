import os
from pathlib import Path
import subprocess
import sys


def test_legacy_migration_preserves_alerts_and_startup_is_repeatable(tmp_path):
    # Run migrations against an isolated file; never use DATABASE_URL from the user's .env.
    environment = dict(os.environ, DATABASE_URL=f"sqlite:///{(tmp_path / 'migration.db').as_posix()}",
                       ENABLE_SCHEDULER="false")
    script = '''
from alembic import command
from alembic.config import Config
from sqlalchemy import text, inspect
from app.database import engine, init_db
config = Config("alembic.ini")
command.upgrade(config, "20260615_0001")
with engine.begin() as conn:
    conn.execute(text("INSERT INTO events (id,title,url,status,content_hash,sale_date,first_seen_at,last_seen_at,created_at,updated_at) VALUES (1,'Artist','https://example.com','active','old','2027-01-01 00:00:00',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    conn.execute(text("INSERT INTO alerts (id,event_id,chat_id,alert_type,message,sent_at,created_at) VALUES (1,1,'123','sale_reminder_1h','old message',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
init_db()
init_db()
with engine.connect() as conn:
    row = conn.execute(text("SELECT delivery_state,alert_type,message FROM alerts")).one()
    assert row == ('sent','sale_reminder_1h:2027-01-01T00:00:00+00:00','old message'), row
    assert conn.scalar(text("SELECT revision FROM events")) == 1
    assert conn.scalar(text("SELECT version_num FROM alembic_version")) == '20260907_0002'
'''
    result = subprocess.run([sys.executable, "-c", script], env=environment,
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_fresh_database_startup(tmp_path):
    environment = dict(os.environ, DATABASE_URL=f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}",
                       ENABLE_SCHEDULER="false")
    result = subprocess.run([sys.executable, "-c", "from app.database import init_db; init_db(); init_db()"],
                            env=environment, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
