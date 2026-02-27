---
schedules:
  - name: daily-report
    cron: "0 9 * * 1-5"
    message: "Generate a daily status report"
    instructions: "Focus on system uptime metrics, error rates, and deployment activity from the last 24 hours. Use bullet points and keep it under 200 words."
    enabled: true
    timezone: "Europe/London"
  - name: heartbeat
    cron: "0 * * * *"
    message: "Generate a one-sentence system heartbeat status"
    instructions: "Respond with exactly one sentence confirming system health. Be concise."
    enabled: true
---

# Scheduled Reporter

You generate periodic summary reports. When invoked, provide a brief
status report with the current date and a summary of system health.
