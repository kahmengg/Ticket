from datetime import datetime, timezone
from scripts.check_schedule_gap import gap_minutes


def test_gap_uses_previous_success_and_excludes_current_run():
    now = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
    runs = [dict(id=3, conclusion="success", updated_at="2026-10-08T12:00:00Z"),
            dict(id=2, conclusion="failure", updated_at="2026-10-08T11:50:00Z"),
            dict(id=1, conclusion="success", updated_at="2026-10-08T10:00:00Z")]
    assert gap_minutes(runs, "3", now) == 120
    assert gap_minutes([], "3", now) is None
