---
schedules:
  - name: daily-report
    cron: "0 9 * * 1-5"
    message: "Generate a daily status report"
    enabled: false
    timezone: "Europe/London"
---

# Scheduled Reporter Configuration

Runs daily at 9am UK time on weekdays (disabled by default for testing).
