# TelegramAIAgent — Documentation

> **Module 3** of the Rappi Early Alerts system.  
> Transforms decision-engine alerts into natural-language Telegram messages using an LLM.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Project Structure](#3-project-structure)
4. [Configuration](#4-configuration)
5. [Components Deep Dive](#5-components-deep-dive)
6. [Alert Pipeline](#6-alert-pipeline)
7. [Telegram Bot Commands](#7-telegram-bot-commands)
8. [Historical Context Data](#8-historical-context-data)
9. [LLM Integration](#9-llm-integration)
10. [Running Locally](#10-running-locally)
11. [Running with Docker](#11-running-with-docker)
12. [Environment Variables Reference](#12-environment-variables-reference)
13. [API Endpoints Consumed](#13-api-endpoints-consumed)
14. [Prompt Engineering](#14-prompt-engineering)
15. [Error Handling](#15-error-handling)
16. [Diagrams](#16-diagrams)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. Overview

TelegramAIAgent is an autonomous service that bridges the **EarlyAlertsAPI** (Module 2 — the decision engine for Rappi's fleet in Monterrey) with a **Telegram chat** used by the Operations Manager. It:

1. **Polls** EarlyAlertsAPI every N seconds for pending alerts.
2. **Generates** a natural-language narrative using an LLM — with the EarlyAlertsAPI Motor documents (calibrated rules + stats) as system context.
3. **Sends** the formatted message to Telegram.
4. **Acknowledges** the alert as consumed via the API.

Additionally, the Operations Manager can interact with the bot directly using Telegram commands (`/check`, `/force_check`, `/status`).

### Key Design Principles

- **Decoupled**: Communicates with EarlyAlertsAPI exclusively via HTTP REST — no shared database.
- **Configurable**: All paths, tokens, models, and intervals are env-var driven.
- **Provider-agnostic**: LLM provider swappable via a single env var (OpenAI, Anthropic, Ollama, Azure).
- **Fault-tolerant**: Failed alerts are retried next cycle; Telegram send failures are logged and skipped.

---

## 2. Architecture

The system follows a simple **poll → generate → send → ack** pipeline, running as a single Python asyncio process with two concurrent tasks:

```
┌──────────────────────────────────────────────────────────────┐
│                    TelegramAIAgent                            │
│                                                              │
│  ┌─────────────┐    ┌─────────────────┐    ┌──────────────┐ │
│  │  Poll Loop   │───▶│ AlertOrchestrator│───▶│ LLMClient    │ │
│  │  (auto mode) │    │                 │    │ (LiteLLM)    │ │
│  └──────┬───────┘    │  ContextSource  │    └──────────────┘ │
│         │            │  PromptBuilder  │                     │
│  ┌──────▼───────┐    └────────┬────────┘    ┌──────────────┐ │
│  │  Telegram    │             │             │ Alerts API   │ │
│  │  Commands    │─────────────┘             │ Consumer     │ │
│  │  (/check,    │                           │ (httpx)      │ │
│  │   /status)   │                           └──────┬───────┘ │
│  └──────────────┘                                  │         │
└──────────────────────────────────────────────────────┼────────┘
                                                       │ HTTP
                                              ┌────────▼────────┐
                                              │ EarlyAlertsAPI   │
                                              │ (Module 2)       │
                                              └─────────────────┘
```

Both the poll loop and the Telegram command listener feed into the **same pipeline**: `AlertOrchestrator.process_alert()`.

---

## 3. Project Structure

```
TelegramAIAgent/
├── pyproject.toml              # Project metadata and dependencies
├── Dockerfile                  # Container build (python:3.13-slim)
├── docker-compose.yml          # Orchestration with EarlyAlertsAPI network
├── .env.example                # Template for environment variables
├── app/
│   ├── __init__.py
│   ├── main.py                 # Entrypoint: poll loop + Telegram listener
│   ├── config.py               # Settings (pydantic-settings, env vars)
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── orchestrator.py     # Pipeline: alert → prompt → LLM → text
│   │   ├── context_source.py   # Loads Motor documents, serves motor context for system prompt
│   │   ├── llm/
│   │   │   ├── __init__.py
│   │   │   └── client.py       # LiteLLM wrapper (provider-agnostic)
│   │   └── prompts/
│   │       ├── __init__.py
│   │       └── system_prompt.py # System prompt + user message templates
│   ├── services/
│   │   ├── __init__.py
│   │   ├── alerts_api/
│   │   │   ├── __init__.py
│   │   │   └── consumer.py     # HTTP client for EarlyAlertsAPI
│   │   └── telegram/
│   │       ├── __init__.py
│   │       ├── sender.py       # send_message() via Bot API
│   │       └── commands.py     # /check, /force_check, /status handlers
│   └── docs/
│       ├── documentation.md    # This file
│       └── diagrams/           # C4 model + sequence diagrams (Mermaid)
├── data/
│   └── historical_context/     # Motor documents from EarlyAlertsAPI (Module 2)
│       ├── Motor_Reglas_y_Alertas.md          # Full calibration doc — injected into system prompt
│       └── Documentacion_Motor_Alertas_Tempranas.md  # Compact operational summary
└── instructions/
    └── PLAN.md                 # Technical specification
```

---

## 4. Configuration

All configuration is managed by `app/config.py` using **pydantic-settings**. Values are read from environment variables or a `.env` file in the project root.

```python
class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str          # From @BotFather
    telegram_chat_id: str            # Target chat for alerts

    # LLM
    llm_model: str = "gpt-4o-mini"  # LiteLLM model string
    llm_api_key: str                 # API key for the provider
    llm_api_base: str | None = None  # Custom endpoint (Azure, Ollama)

    # EarlyAlertsAPI
    alerts_api_base_url: str = "http://localhost:8000"
    poll_interval_seconds: int = 120

    # Motor document paths (overridable — update when rules are recalibrated)
    motor_rules_path: str = "data/historical_context/Motor_Reglas_y_Alertas.md"
    motor_docs_path: str = "data/historical_context/Documentacion_Motor_Alertas_Tempranas.md"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
```

---

## 5. Components Deep Dive

### 5.1 AlertOrchestrator (`app/agent/orchestrator.py`)

The central pipeline that transforms a raw alert dict into a Telegram-ready message:

1. **Map risk level** to display label (`medio → MEDIO`, `alto → ALTO`, `critico → CRÍTICO`).
2. **Build user message** from the alert payload fields (zone, precip, ratio, earnings, etc.).
3. **Call LLM** with the system prompt (containing Motor context) and the user message.
4. **Return** the LLM-generated text.

### 5.2 ContextSourceService (`app/agent/context_source.py`)

Loads the Motor documents at startup and exposes a single method:

| Method | Returns |
|---|---|
| `get_motor_context()` | `Motor_Reglas_y_Alertas.md` + `---` + `Documentacion_Motor_Alertas_Tempranas.md` as one string |
| `reload()` | Re-reads both files from disk |

The returned string is injected verbatim into the LLM system prompt at startup. It contains all calibrated rules, thresholds, and stats from Module 1 as synthesized and applied by the EarlyAlertsAPI engine — a richer and more actionable context than the raw Module 1 CSVs.

### 5.3 LLMClient (`app/agent/llm/client.py`)

Provider-agnostic LLM wrapper using [LiteLLM](https://docs.litellm.ai/):

- Uses `litellm.acompletion()` for async chat completions.
- Model, API key, and base URL come from `Settings`.
- 30-second timeout per call.
- Raises `RuntimeError` on failure.

**Switching providers** requires only env var changes:

| Provider | `LLM_MODEL` | `LLM_API_KEY` | `LLM_API_BASE` |
|---|---|---|---|
| OpenAI | `gpt-4o-mini` | `sk-...` | (not needed) |
| Anthropic | `anthropic/claude-3-haiku-20240307` | `sk-ant-...` | (not needed) |
| Ollama (local) | `ollama/llama3` | (any string) | `http://localhost:11434` |
| Azure OpenAI | `azure/deployment-name` | Azure key | `https://your-resource.openai.azure.com` |

### 5.4 AlertsAPIConsumer (`app/services/alerts_api/consumer.py`)

HTTP client for EarlyAlertsAPI using `httpx.AsyncClient`:

| Method | HTTP | Endpoint | Timeout | Notes |
|---|---|---|---|---|
| `fetch_pending_alerts()` | `GET` | `/api/v1/alerts/latest?status=pending&limit=50` | 15s | Returns `list[dict]` |
| `mark_consumed(alert_id)` | `PATCH` | `/api/v1/alerts/{id}/consume` | 15s | 404-tolerant (logs warning) |
| `trigger_run_once()` | `POST` | `/api/v1/jobs/run-once` | 60s | Forces a full engine cycle |
| `get_health()` | `GET` | `/api/v1/health` | 15s | Returns health + last_run |

### 5.5 Telegram Sender (`app/services/telegram/sender.py`)

Simple `send_message()` function:

- Posts to `https://api.telegram.org/bot{token}/sendMessage`.
- Truncates messages to **4096 characters** (Telegram hard limit).
- Returns `True` on success, `False` on failure (with logging).
- Uses `httpx` directly (no python-telegram-bot dependency for sending).

### 5.6 Telegram Commands (`app/services/telegram/commands.py`)

Builds a `python-telegram-bot` `Application` with three command handlers:

| Command | Behavior |
|---|---|
| `/check` | Fetch pending alerts → process → send. If none: reply with BAJO status. |
| `/force_check` | Trigger `POST /jobs/run-once` first → then fetch + process → send. |
| `/status` | Report EarlyAlertsAPI health: last_run, open_events, scheduler state. |

---

## 6. Alert Pipeline

Both automatic and manual modes follow the same pipeline:

```
1. FETCH       AlertsAPIConsumer.fetch_pending_alerts()
                    → GET /api/v1/alerts/latest?status=pending
                    → list[dict] with zone, risk_level, precip_mm, projected_ratio,
                      recommended_earnings_mxn, uplift_mxn, lead_time_min,
                      secondary_zones, reason, forecast_time

2. PROMPT      build_user_message(alert, risk_display)
                    → Formatted string with alert payload fields only
               build_system_prompt(motor_context)
                    → System prompt with role, rules, and full Motor documents
                      (Motor_Reglas_y_Alertas.md + Documentacion_Motor_Alertas_Tempranas.md)

3. GENERATE    LLMClient.generate(system_prompt, user_message)
                    → litellm.acompletion() → formatted Telegram message text

4. SEND        send_message(bot_token, chat_id, text)
                    → POST to Telegram Bot API /sendMessage

5. ACK         AlertsAPIConsumer.mark_consumed(alert_id)
                    → PATCH /api/v1/alerts/{id}/consume
```

### Output Message Format

The LLM is instructed to produce messages with exactly 5 sections:

```
🚨 ZONA + NIVEL DE RIESGO
📊 QUÉ SE ESPERA (2-3 lines with historical stats)
💰 ACCIÓN (specific earnings adjustment)
⏱️ VENTANA (time to act)
📍 ZONAS SECUNDARIAS
```

---

## 7. Telegram Bot Commands

### Setup: Creating the Bot

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts to create your bot.
3. Copy the **bot token** (format: `123456:ABC-DEF...`).
4. Add the bot to the target chat/group.
5. Get the **chat ID**:
   - Send a message in the chat.
   - Visit `https://api.telegram.org/bot<TOKEN>/getUpdates`.
   - Find the `chat.id` field in the response.

### Available Commands

| Command | Description | Use Case |
|---|---|---|
| `/check` | Check for pending alerts right now | Quick manual verification |
| `/force_check` | Force a full engine cycle + check | On-demand evaluation (demo, incident response) |
| `/status` | Show engine health status | Monitoring, debugging |

### Example Interactions

**When alerts exist:**
```
User: /check
Bot: 🔍 Consultando alertas pendientes...
Bot: 🚨 Santiago ALTO
     📊 Se espera saturación en la zona Santiago...
     💰 Subir earnings de 55.6 a 80.0 MXN (+24.4 MXN)
     ⏱️ 60 minutos para actuar
     📍 Carretera Nacional
```

**When no alerts (BAJO):**
```
User: /check
Bot: 🔍 Consultando alertas pendientes...
Bot: ✅ Sin riesgo inminente — Nivel: BAJO
     Última ejecución del motor: 2026-03-27T14:00:00
     Eventos abiertos: 0
```

---

## 8. Historical Context Data

The `data/historical_context/` directory contains the Motor documents from EarlyAlertsAPI (Module 2) that are injected into the LLM system prompt:

| File | Size | Description |
|---|---|---|
| `Motor_Reglas_y_Alertas.md` | ~300 lines | Full calibration document: all thresholds, rain lifts, earnings targets, severity levels, event memory rules, and secondary zone ranking — each rule traced to `[M1-P1]`...`[CALC-1]` |
| `Documentacion_Motor_Alertas_Tempranas.md` | ~60 lines | Compact operational summary of the same rules |

### Why these documents (not the raw Module 1 CSVs)

EarlyAlertsAPI already consumed and **processed** all Module 1 data. Every value in the alert payload — `projected_ratio`, `risk_level`, `recommended_earnings_mxn`, `secondary_zones` — was computed by the engine using rules calibrated from that data. The Motor documents explain **why** those numbers are what they are (e.g. why 80 MXN, why Santiago triggers at 1.0 mm/hr, why the ratio lifts used). The LLM needs this context to write an informed narrative — not the raw CSVs.

### Updating Context Data

If the Motor documents are updated (e.g. rules recalibrated with new data):

1. Copy updated files to `data/historical_context/`.
2. If paths changed, update env vars:
   ```bash
   MOTOR_RULES_PATH=data/historical_context/Motor_Reglas_y_Alertas_v2.md
   MOTOR_DOCS_PATH=data/historical_context/Documentacion_v2.md
   ```
3. Restart the agent (or call `reload()`).

---

## 9. LLM Integration

### How It Works

1. **System prompt** (built once at startup):
   - Defines the role: "Eres un asistente de alertas operativas..."
   - Sets strict formatting rules (5 sections, Spanish, no Markdown, 10-second readability).
   - Injects the full `Motor_Reglas_y_Alertas.md` + `Documentacion_Motor_Alertas_Tempranas.md` between `---` delimiters. The LLM receives all calibrated thresholds, historical stats, and rule justifications (e.g. why 80 MXN, why 2.0 mm/hr triggers, why Santiago fires at 1.0 mm/hr, the exact ratio lifts and saturation percentages).

2. **User message** (built per alert from the alert payload):
   - Zone, risk level, precipitation, projected ratio, earnings recommendation, uplift, lead time, secondary zones, reason, forecast time.
   - No CSV lookups or per-alert enrichment needed — all decisions are pre-computed by the engine.

3. **Generation**:
   - `litellm.acompletion()` sends both messages to the configured provider.
   - Returns the generated text directly — no post-processing.

### Token Budget

- **System prompt**: ~6,000 tokens (Motor documents, fixed per call).
- **User message**: ~150 tokens per alert.
- **Response**: ~200 tokens per alert.
- **Estimated cost** (GPT-4o-mini): ~$0.001 per alert ($0.15/M input, $0.60/M output).

---

## 10. Running Locally

### Prerequisites

- Python 3.13+
- EarlyAlertsAPI running (default: `http://localhost:8000`)
- Telegram bot token and chat ID
- LLM API key (OpenAI, Anthropic, etc.)

### Step 1: Create Virtual Environment

```bash
cd TelegramAIAgent
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate
```

### Step 2: Install Dependencies

```bash
# Option A: Using pip
pip install -e .

# Option B: Using uv (recommended — handles long paths on Windows)
pip install uv
uv pip install -e .
```

### Step 3: Configure Environment

```bash
# Copy the example and fill in real values
cp .env.example .env
```

Edit `.env`:
```ini
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=-1001234567890
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...your-key...
ALERTS_API_BASE_URL=http://localhost:8000
POLL_INTERVAL_SECONDS=120
```

### Step 4: Run

```bash
python -m app.main
```

Expected output:
```
2026-03-27 14:00:00 [INFO] app.agent.context_source — Loading historical context from configured paths...
2026-03-27 14:00:00 [INFO] app.agent.context_source — Historical context loaded successfully.
2026-03-27 14:00:00 [INFO] app.main — Starting TelegramAIAgent (model: gpt-4o-mini)
2026-03-27 14:00:00 [INFO] app.main — Telegram command listener started.
2026-03-27 14:00:00 [INFO] app.main — Poll loop started (interval: 120s)
```

### Step 5: Test Manually

In Telegram, send `/check` to the bot. If no alerts are pending, you'll see the BAJO response.

To force an alert:
1. Lower the trigger threshold in EarlyAlertsAPI's `rule_pack_v1.yaml` (e.g., `triggers.base_mm: 0.0`).
2. Rebuild EarlyAlertsAPI: `cd ../EarlyAlertsAPI && docker compose up -d --build`.
3. Send `/force_check` in Telegram.

---

## 11. Running with Docker

### Prerequisites

- Docker and Docker Compose installed.
- EarlyAlertsAPI running in Docker (creates the `earlyalertsapi_default` network).

### Step 1: Configure Environment

```bash
cd TelegramAIAgent
cp .env.example .env
# Edit .env with real values (same as local setup)
```

### Step 2: Build and Run

```bash
docker compose up -d --build
```

This will:
1. Build the image from `Dockerfile` (python:3.13-slim base).
2. Install dependencies via `pip install .`.
3. Start the container connected to the `earlyalertsapi_default` network.
4. Mount `./data` as read-only at `/app/data` inside the container.

### Step 3: Check Logs

```bash
docker compose logs -f telegram-agent
```

### Step 4: Stop

```bash
docker compose down
```

### Docker Compose Configuration

```yaml
services:
  telegram-agent:
    build: .
    env_file: .env
    environment:
      # Override API URL to reach EarlyAlertsAPI inside Docker network
      ALERTS_API_BASE_URL: http://earlyalertsapi-api-1:8000
    networks:
      - earlyalertsapi_default
    restart: unless-stopped
    volumes:
      - ./data:/app/data:ro

networks:
  earlyalertsapi_default:
    external: true
```

Key details:
- **Network**: Joins the external `earlyalertsapi_default` network so it can reach EarlyAlertsAPI by container name.
- **API URL override**: Inside Docker, the API is at `http://earlyalertsapi-api-1:8000` (not `localhost`).
- **Volume mount**: `./data` mounted read-only so CSV/MD files are accessible inside the container.
- **Restart policy**: `unless-stopped` — auto-restarts on crash.

### Dockerfile Explained

```dockerfile
FROM python:3.13-slim
WORKDIR /app

# Build dependencies for compiled packages
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cache layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir hatchling && pip install --no-cache-dir .

# Copy application code
COPY . .

CMD ["python", "-m", "app.main"]
```

### Running Both Services Together

If EarlyAlertsAPI is not yet running:

```bash
# Terminal 1: Start EarlyAlertsAPI
cd ../EarlyAlertsAPI
docker compose up -d --build

# Terminal 2: Start TelegramAIAgent
cd ../TelegramAIAgent
docker compose up -d --build

# Check both are running
docker ps
```

---

## 12. Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Yes | — | Target chat ID for alert messages |
| `LLM_MODEL` | No | `gpt-4o-mini` | LiteLLM model string |
| `LLM_API_KEY` | Yes | — | API key for the LLM provider |
| `LLM_API_BASE` | No | `None` | Custom API base URL (Azure, Ollama) |
| `ALERTS_API_BASE_URL` | No | `http://localhost:8000` | EarlyAlertsAPI URL |
| `POLL_INTERVAL_SECONDS` | No | `120` | Auto-poll interval in seconds |
| `MOTOR_RULES_PATH` | No | `data/historical_context/Motor_Reglas_y_Alertas.md` | Full calibration rules document |
| `MOTOR_DOCS_PATH` | No | `data/historical_context/Documentacion_Motor_Alertas_Tempranas.md` | Compact operational summary |

---

## 13. API Endpoints Consumed

TelegramAIAgent consumes the following EarlyAlertsAPI endpoints:

### `GET /api/v1/alerts/latest?status=pending&limit=50`

Fetch pending alerts from the outbox. Returns an array of alert dicts:

```json
[
  {
    "id": "abc-123",
    "zone": "Santiago",
    "risk_level": "alto",
    "precip_mm": 4.2,
    "projected_ratio": 2.44,
    "recommended_earnings_mxn": 80.0,
    "uplift_mxn": 24.4,
    "lead_time_min": 60,
    "secondary_zones": ["Carretera Nacional"],
    "reason": "Precipitación 4.2 mm/hr >= trigger 2.0",
    "forecast_time": "2026-03-27T14:00:00",
    "status": "pending"
  }
]
```

### `PATCH /api/v1/alerts/{alert_id}/consume`

Mark an alert as consumed. Added by Module 3 to EarlyAlertsAPI (purely additive — no existing behavior changed).

```json
{"status": "consumed", "id": "abc-123"}
```

### `POST /api/v1/jobs/run-once`

Trigger a full forecast → evaluate → emit cycle. Used by `/force_check`:

```json
{"alerts_emitted": 3, "run_id": "..."}
```

### `GET /api/v1/health`

Engine health check:

```json
{"last_run": "2026-03-27T14:00:00", "open_events": 2, "scheduler": "running"}
```

---

## 14. Prompt Engineering

### Design Principle

EarlyAlertsAPI (Module 2) already consumed and processed all Module 1 historical data. Every value in the alert payload is pre-computed by the engine using calibrated rules. The LLM's job is purely **narration** — explaining the "why" behind numbers the engine already decided.

This means:
- The system prompt contains the **Motor documents** (the rule calibration source of truth).
- The user message contains only the **alert payload** fields.
- No per-alert CSV lookups or data re-processing are needed.

### System Prompt Structure

The system prompt has three parts:

1. **Role definition**: "Eres un asistente de alertas operativas para la flota de repartidores de Rappi en Monterrey."
2. **Strict rules** (5 mandatory sections, Spanish, no Markdown, specific numbers, 10-second readability).
3. **Motor context**: `Motor_Reglas_y_Alertas.md` + `Documentacion_Motor_Alertas_Tempranas.md` injected verbatim. This gives the LLM:
   - All calibrated thresholds (2.0 mm/hr base, 1.0 mm/hr for sensitive zones in peak)
   - Rain lift values and projected ratio lookup logic
   - Earnings target justification (80 MXN from Q4 historical analysis)
   - Sensitivity ranking for all 14 zones
   - Saturation statistics by zone, hour, and rain bucket
   - Cooldown and event memory rules

### User Message

Contains only what the engine computed for this specific alert:
- Zone, risk level, precipitation, projected ratio, earnings recommendation, uplift, lead time, secondary zones, engine reason, forecast time.

The LLM cross-references these fields with the Motor context in the system prompt to produce an accurate, evidence-based narrative.

---

## 15. Error Handling

| Scenario | Behavior |
|---|---|
| EarlyAlertsAPI unreachable | Poll loop logs exception, sleeps, retries next cycle |
| Single alert processing fails | Logged and skipped; other alerts continue |
| LLM call fails (timeout/error) | `RuntimeError` raised, alert skipped, retried next cycle |
| Telegram send fails | Returns `False`, alert NOT marked consumed → retried next cycle |
| Alert already consumed (404 on PATCH) | Logged as warning, skipped (not an error) |
| Motor document not found at startup | `FileNotFoundError` — application fails to start (intentional: Motor context is required) |

---

## 16. Diagrams

Detailed architectural diagrams are available in `app/docs/diagrams/`:

| File | Description |
|---|---|
| `c1_system_context.md` | **C1 — System Context**: TelegramAIAgent in its environment (users, external systems) |
| `c2_container.md` | **C2 — Container**: Deployable units within the system boundary |
| `c3_component.md` | **C3 — Component**: Internal modules and their interactions |
| `c4_code.md` | **C4 — Code**: Classes, methods, data structures, and data flow |
| `sequence_diagrams.md` | **Sequence**: Step-by-step message flow for auto poll, /check, /force_check, and startup |

All diagrams use [Mermaid](https://mermaid.js.org/) syntax and render natively in GitHub, GitLab, VS Code (with extensions), and most Markdown viewers.

---

## 17. Troubleshooting

### Agent starts but no alerts appear

1. Check EarlyAlertsAPI is running: `curl http://localhost:8000/api/v1/health`
2. Verify there are pending alerts: `curl http://localhost:8000/api/v1/alerts/latest?status=pending`
3. If no pending alerts, lower the trigger threshold or use `/force_check`.

### "LLM generation failed" errors

1. Verify `LLM_API_KEY` is correct.
2. Check the model string: `LLM_MODEL=gpt-4o-mini` (not `openai/gpt-4o-mini` for OpenAI).
3. If using Ollama, ensure `LLM_API_BASE=http://localhost:11434` is set and Ollama is running.

### Telegram messages not arriving

1. Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are correct.
2. Test the bot: `curl https://api.telegram.org/bot<TOKEN>/getMe` — should return bot info.
3. Ensure the bot is added to the target chat and has permission to send messages.

### Docker: "network earlyalertsapi_default not found"

EarlyAlertsAPI must be running first to create the network:
```bash
cd ../EarlyAlertsAPI
docker compose up -d
```

### Docker: Agent can't reach EarlyAlertsAPI

Verify the container name matches the `ALERTS_API_BASE_URL`:
```bash
docker ps --format "{{.Names}}"
# Look for the EarlyAlertsAPI container name (e.g., earlyalertsapi-api-1)
```

Update `docker-compose.yml` if the name differs.

### Windows: pip install fails with long path error

Use `uv` instead of `pip`:
```bash
pip install uv
uv pip install -e .
```

### Historical context shows None values

Check that the CSV files exist at the configured paths and contain the expected columns. The agent logs the load status at startup:
```
[INFO] app.agent.context_source — Historical context loaded successfully.
```

If this message doesn't appear, check file paths in `.env` or the defaults in `config.py`.
