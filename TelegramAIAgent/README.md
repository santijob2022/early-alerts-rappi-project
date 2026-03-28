# TelegramAIAgent

LLM-powered Telegram bot that polls [EarlyAlertsAPI](../EarlyAlertsAPI) for pending alerts and narrates them in natural language. Built with `python-telegram-bot`, `LiteLLM`, and `pydantic-settings`.

---

## Table of Contents

1. [Architecture overview](#1-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [One-time setup: Telegram bot](#3-one-time-setup-telegram-bot)
4. [Environment variables](#4-environment-variables)
5. [Running with Docker (recommended)](#5-running-with-docker-recommended)
6. [Running locally (development)](#6-running-locally-development)
7. [Using the bot from Telegram](#7-using-the-bot-from-telegram)
8. [Running the test suite](#8-running-the-test-suite)

---

## 1. Architecture overview

```
Telegram user
     │
     │  /check  /force_check  /status
     ▼
TelegramAIAgent  ──poll every N seconds──▶  EarlyAlertsAPI
     │                                           │
     │  fetch pending alerts                     │  alert engine (APScheduler)
     │  ask LLM to narrate                       │  DuckDB forecast data
     │  send to Telegram chat                    │  SQLite alert store
     └───────────────────────────────────────────┘
```

- **EarlyAlertsAPI** runs independently (two containers: `api` + `scheduler`).
- **TelegramAIAgent** joins the same Docker network and talks to the API container by hostname.

---

## 2. Prerequisites

| Tool | Version |
|---|---|
| Docker Desktop | 4.x or newer |
| Docker Compose | v2 (included with Docker Desktop) |
| Python | 3.13+ (for local development only) |
| Telegram account | any |

> **Windows note**: all commands below use PowerShell or Git Bash. Replace `\` path separators as needed.

---

## 3. One-time setup: Telegram bot

You only do this once. Skip if you already have a bot token and chat ID.

### 3.1 Create the bot

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts (choose a name and a username ending in `bot`).
3. BotFather replies with a token like `123456789:<YOUR_TELEGRAM_BOT_TOKEN>`.  
   **Copy it** — this is your `TELEGRAM_BOT_TOKEN`.

### 3.2 Get your chat ID

1. Send any message to your new bot from your Telegram account.
2. Open this URL in a browser (replace `<TOKEN>` with your token):
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. Find `"chat":{"id":` in the JSON. The number next to it is your `TELEGRAM_CHAT_ID`.

   Alternatively, forward any message to **@userinfobot** — it replies with your chat ID directly.

---

## 4. Environment variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Open `.env` and set:

```dotenv
# Required
TELEGRAM_BOT_TOKEN=123456789:<YOUR_TELEGRAM_BOT_TOKEN>
TELEGRAM_CHAT_ID=987654321
LLM_API_KEY=sk-...your-openai-or-anthropic-key

# Optional — defaults shown
LLM_MODEL=gpt-4o-mini
POLL_INTERVAL_SECONDS=120

# Only needed if running locally (not in Docker)
ALERTS_API_BASE_URL=http://localhost:8000
```

> When running in Docker the compose file overrides `ALERTS_API_BASE_URL` automatically to reach the API container by its internal hostname, so you do **not** need to set it manually for Docker runs.

---

## 5. Running with Docker (recommended)

### Step 1 — Start EarlyAlertsAPI first

The agent depends on EarlyAlertsAPI being healthy. From the `EarlyAlertsAPI/` folder:

```bash
cd ../EarlyAlertsAPI
cp .env.example .env    # if you haven't already
docker compose up --build -d
```

Wait until both containers are healthy:

```bash
docker compose ps
# api       running (healthy)
# scheduler running
```

You can also verify the API is up:

```bash
curl http://localhost:8000/api/v1/health
```

### Step 2 — Build and start TelegramAIAgent

From the `TelegramAIAgent/` folder:

```bash
cd ../TelegramAIAgent
docker compose up --build -d
```

This builds the image, attaches the container to the `earlyalertsapi_default` network, and mounts `./data` read-only so the LLM context files are available.

### Step 3 — Verify the agent is running

```bash
docker compose logs -f
```

You should see lines like:

```
INFO  app.main - Motor context loaded (rules 4321 chars, docs 2198 chars)
INFO  app.main - Poll loop started — interval 120s
INFO  app.main - Application started. Bot is running.
```

### Stopping everything

```bash
# Agent only
docker compose down

# EarlyAlertsAPI only
cd ../EarlyAlertsAPI && docker compose down

# Both + remove volumes (wipes alert DB)
docker compose down -v
```

### Rebuilding after code changes

Any change to Python files, `pyproject.toml`, or `data/` requires a rebuild:

```bash
docker compose up --build -d
```

---

## 6. Running locally (development)

Use this when you want faster iteration without rebuilding Docker images.

### Step 1 — Create and activate a virtual environment

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS / Linux / Git Bash
source .venv/bin/activate
```

### Step 2 — Install dependencies

```bash
pip install -e ".[dev]"
```

### Step 3 — Set environment variables

Make sure `.env` exists with all required values (see [Section 4](#4-environment-variables)).  
`ALERTS_API_BASE_URL` must point to the running EarlyAlertsAPI instance:

```dotenv
ALERTS_API_BASE_URL=http://localhost:8000
```

EarlyAlertsAPI must be running in Docker (or locally) and reachable at that URL.

### Step 4 — Run the agent

```bash
python -m app.main
```

---

## 7. Using the bot from Telegram

Once the agent is running, open Telegram and find your bot by its username.

### Available commands

| Command | What it does |
|---|---|
| `/check` | Fetches any pending (unconsumed) alerts from EarlyAlertsAPI and sends each one as an LLM-narrated message. Reports "Sin riesgo inminente — Nivel: BAJO" if no alerts are pending. |
| `/force_check` | Triggers a fresh engine evaluation cycle in EarlyAlertsAPI first, then fetches and narrates any resulting alerts. Use this when you want an on-demand analysis rather than waiting for the next scheduled run. |
| `/status` | Shows the current health of EarlyAlertsAPI: last engine run time and number of open events. |

### Automatic polling

The agent also polls EarlyAlertsAPI every `POLL_INTERVAL_SECONDS` (default: 120 s) in the background. Whenever a new alert is published by the engine, the bot sends it to `TELEGRAM_CHAT_ID` automatically — no command needed.

### Message format

Each narrated alert contains five sections produced by the LLM:

1. **Risk level** (BAJO / MEDIO / ALTO / CRITICO) with a colour emoji
2. **What is happening** — plain-language description of the situation
3. **Why it matters** — business impact context
4. **Recommended action** — one concrete next step
5. **Data confidence** — how reliable the underlying signal is

---

## 8. Running the test suite

The project ships with 94 tests organised in `tests/unit/` and `tests/integration/`.

### 8.1 Prerequisites

The dev dependencies must be installed (see [Section 6, Step 2](#step-2--install-dependencies)).  
No running services are needed — all HTTP calls are mocked.

### 8.2 Run all tests

```bash
pytest
```

### 8.3 Run with coverage report

```bash
pytest --cov=app --cov-report=term-missing
```

### 8.4 Run a specific module

```bash
pytest tests/unit/test_system_prompt.py -v
pytest tests/integration/ -v
```

### 8.5 Expected output

```
======== 94 passed in ~15s ========
```

Coverage for all core logic modules (`context_source`, `llm/client`, `orchestrator`, `system_prompt`, `config`, `consumer`, `sender`) is **100%**. Entry-point wiring (`main.py`, `commands.py`) is excluded as it requires a live Telegram connection.

See [app/docs/test_report.md](app/docs/test_report.md) for the full coverage and complexity report.
