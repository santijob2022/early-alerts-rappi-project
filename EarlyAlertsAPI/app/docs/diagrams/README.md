# Architecture Diagrams – EarlyAlertsAPI

All diagrams use [Mermaid](https://mermaid.js.org/) and render natively in GitHub, GitLab, and VS Code (with the Markdown Preview Mermaid Support extension).

## C4 Model

| File | Level | What it shows |
|---|---|---|
| [c1_system_context.md](c1_system_context.md) | C1 – Context | EarlyAlertsAPI and its external actors (Open-Meteo, Module 3, Operations team) |
| [c2_container.md](c2_container.md) | C2 – Container | API container, Scheduler container, SQLite, DuckDB, YAML config files |
| [c3_component.md](c3_component.md) | C3 – Component | Components inside `app/backend`: Orchestrator, Decision Engine, Ingestion, State Repos, Config |
| [c4_code.md](c4_code.md) | C4 – Code | Class / function signatures, ER diagram of SQLite tables, orchestrator → repo call graph |

## Sequence Diagrams

| File | Scenario |
|---|---|
| [sequence_diagrams.md](sequence_diagrams.md) → SD-1 | Full alert cycle (`run_cycle`) end-to-end |
| [sequence_diagrams.md](sequence_diagrams.md) → SD-2 | Module 3 outbox consumption (Telegram Bot) |
| [sequence_diagrams.md](sequence_diagrams.md) → SD-3 | GET /alerts/latest REST request |
| [sequence_diagrams.md](sequence_diagrams.md) → SD-4 | POST /jobs/run-once manual trigger |
| [sequence_diagrams.md](sequence_diagrams.md) → SD-5 | FastAPI startup lifespan |
