"""Report missed reminder cadence using GitHub run history, without any app secrets."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess


def gap_minutes(runs, current_id, now):
    completed = [datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
                 for run in runs if str(run["id"]) != str(current_id) and run.get("conclusion") == "success"]
    return (now - max(completed)).total_seconds() / 60 if completed else None


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    response = subprocess.run(["gh", "api", f"repos/{repo}/actions/workflows/scheduled-reminders.yml/runs?per_page=100"],
                              capture_output=True, text=True, check=True)
    gap = gap_minutes(json.loads(response.stdout)["workflow_runs"], os.environ["GITHUB_RUN_ID"], datetime.now(timezone.utc))
    if gap is None or gap > 90:
        reason = "No recent successful reminder run" if gap is None else f"Reminder scheduling gap: {gap:.0f} minutes"
        # Keep delivery running; this annotation makes missed cadence visible to the operator.
        print(f"::warning::{reason}. Timely reminders cannot be guaranteed until the external scheduler is configured.")
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as report:
            report.write(f"## Scheduling needs attention\n{reason}. See REMINDER_SCHEDULING.md.\n")


if __name__ == "__main__":
    main()
