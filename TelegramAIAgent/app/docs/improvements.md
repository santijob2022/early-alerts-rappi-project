# Improvements Backlog — TelegramAIAgent

---

## 1. `/reload_context` Telegram command

**Status**: Not implemented — `ContextSourceService.reload()` exists but nothing triggers it.

**Motivation**: When the Motor documents (`Motor_Reglas_y_Alertas.md`, `Documentacion_Motor_Alertas_Tempranas.md`) are updated with recalibrated rules, the agent currently requires a full container restart to pick up the new content. A `/reload_context` command would allow the Operations Manager to hot-reload the Motor context without downtime.

**Implementation sketch** (`app/services/telegram/commands.py`):

```python
async def reload_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/reload_context — reload Motor documents from disk into the system prompt."""
    try:
        context_service.reload()
        new_prompt = build_system_prompt(context_service.get_motor_context())
        orchestrator._system_prompt = new_prompt
        await update.message.reply_text("✅ Motor context reloaded successfully.")
    except Exception as exc:
        logger.exception("Failed to reload Motor context")
        await update.message.reply_text(f"❌ Reload failed: {exc}")

app.add_handler(CommandHandler("reload_context", reload_context))
```

`context_service` and `orchestrator` would need to be closed over in `build_application()`, following the same pattern as the existing `/check` and `/force_check` handlers.

**When to use**: After updating the Motor MD files on disk (e.g. rules recalibrated with new data) without restarting the container. For normal deployments a `docker compose up --build -d` remains the recommended approach.

---

## 2. Structured output for LLM responses

**Status**: Not implemented — `LLMClient.generate()` returns a raw free-text string with no format validation.

**Motivation**: The system prompt instructs the LLM to produce exactly 5 emoji-headed sections (🚨📊💰⏱️📍). Compliance is prompt-only — if the model drifts, a malformed message is sent to Telegram with no error raised. Structured output would enforce the format at runtime.

**Recommended approach — JSON structured output (Option A)**

Define a Pydantic model for the 5 sections and pass it as `response_format` to LiteLLM:

```python
# app/agent/prompts/system_prompt.py
from pydantic import BaseModel

class AlertMessage(BaseModel):
    zona_riesgo: str        # content for 🚨 line
    que_se_espera: str      # content for 📊 block (2-3 lines)
    accion: str             # content for 💰 line
    ventana: str            # content for ⏱️ line
    zonas_secundarias: str  # content for 📍 line

    def to_telegram_text(self) -> str:
        return (
            f"🚨 {self.zona_riesgo}\n"
            f"📊 {self.que_se_espera}\n"
            f"💰 {self.accion}\n"
            f"⏱️ {self.ventana}\n"
            f"📍 {self.zonas_secundarias}"
        )
```

```python
# app/agent/llm/client.py — add to generate() kwargs
response_format=AlertMessage,
```

```python
# app/agent/orchestrator.py — parse and reassemble
from app.agent.prompts.system_prompt import AlertMessage
raw = await self._llm.generate(self._system_prompt, user_message)
return AlertMessage.model_validate_json(raw).to_telegram_text()
```

If the model omits a field, Pydantic raises a `ValidationError` immediately — the malformed message never reaches Telegram.

**Alternative — lightweight post-generation validation (Option B)**

Keep free-text generation, add a validator in `orchestrator.py`:

```python
_REQUIRED_SECTIONS = ["🚨", "📊", "💰", "⏱️", "📍"]

def _validate_format(text: str) -> None:
    missing = [s for s in _REQUIRED_SECTIONS if s not in text]
    if missing:
        raise ValueError(f"LLM response missing sections: {missing}")
```

Simpler to implement and provider-agnostic, but allows partial drift (wrong content, correct emojis).

**Provider compatibility**: `response_format` with Pydantic models works natively with OpenAI (`gpt-4o-mini`). LiteLLM handles translation for Anthropic and other providers where possible. Option B works with all providers.
