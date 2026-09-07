"""Serialize source checks across scheduler jobs and manual API calls."""
from contextlib import contextmanager
from pathlib import Path
import os
import threading

from sqlalchemy import text

_memory_lock = threading.Lock()


class CheckAlreadyRunning(RuntimeError):
    pass


@contextmanager
def source_check_lock(engine):
    if engine.dialect.name == "postgresql":
        # Hold a dedicated session-level lock across commits in the processing session.
        with engine.connect() as connection:
            acquired = connection.scalar(text("SELECT pg_try_advisory_lock(84729101)"))
            try:
                yield bool(acquired)
            finally:
                if acquired:
                    connection.execute(text("SELECT pg_advisory_unlock(84729101)"))
        return
    database = engine.url.database
    if not database or database == ":memory:":
        acquired = _memory_lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                _memory_lock.release()
        return
    # SQLite deployments share a database file; the OS releases its companion lock on exit.
    lock_path = Path(database).resolve().with_suffix(".check.lock")
    with lock_path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        acquired = False
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            pass
        try:
            yield acquired
        finally:
            if acquired:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
