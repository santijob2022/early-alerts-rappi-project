# C1 – System Context Diagram

Shows **EarlyAlertsAPI** in its environment: who uses it and which external systems it interacts with.

```mermaid
C4Context
    title System Context – EarlyAlertsAPI (Module 2c)

    Person(ops, "Operations Team", "Monitors alert inbox and acts on pricing recommendations")
    Person(dev, "Developer / Scheduler Process", "Triggers forecast cycles via CLI or container")

    System(earlyAlerts, "EarlyAlertsAPI", "Weather-driven alert engine. Polls rain forecasts, evaluates risk per zone, and writes structured alerts to an outbox for downstream consumption.")

    System_Ext(openMeteo, "Open-Meteo API", "Free weather forecast API providing hourly precipitation data for 14 Monterrey zones")
    System_Ext(module3, "Module 3 – Telegram Bot", "LLM + Telegram notifier. Consumes the alert outbox and sends messages to earners (drivers).")

    Rel(dev, earlyAlerts, "Triggers alert cycle", "CLI / HTTP POST /jobs/run-once")
    Rel(earlyAlerts, openMeteo, "Fetches hourly precipitation forecast", "HTTPS / JSON")
    Rel(earlyAlerts, module3, "Provides structured alerts via outbox table", "SQLite alert_outbox (Module 3 boundary)")
    Rel(ops, earlyAlerts, "Reads open events, latest alerts, job status", "HTTP REST API")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## Key points

| Participant | Role |
|---|---|
| **Open-Meteo** | Only external network dependency. One batch HTTPS call per cycle for all 14 zone centroids. |
| **alert_outbox** | Formal handoff table to Module 3. Module 3 never re-fetches weather data. |
| **Operations** | Reads REST API for monitoring (`/health`, `/alerts/latest`, `/events/open`). |
| **Scheduler process** | Triggers `run_cycle()` periodically; runs in a dedicated container to avoid duplicate cycles. |
