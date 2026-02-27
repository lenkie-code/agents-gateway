"""Seed a demo admin schedule to exercise the admin schedules feature.

Usage:
    uv run python seed_admin_schedule.py
"""

import httpx

BASE_URL = "http://localhost:8000"
AUTH = {"Authorization": "Bearer dev-api-key-change-me"}

resp = httpx.post(
    f"{BASE_URL}/v1/schedules",
    json={
        "agent_id": "scheduled-reporter",
        "name": "weekly-summary",
        "cron_expr": "0 10 * * 1",
        "message": "Generate a weekly summary report",
        "instructions": (
            "Summarize the key events from the past week. "
            "Include notable incidents, deployments, and metrics trends."
        ),
        "timezone": "Europe/London",
    },
    headers=AUTH,
)

if resp.status_code == 201:
    print(f"Created: {resp.json()['schedule_id']}")
elif resp.status_code == 409:
    print("Already exists (skipped)")
else:
    print(f"Error {resp.status_code}: {resp.json()}")
