# C1 — System Context Diagram

> Shows the TelegramAIAgent system in context: who uses it, and what external systems it interacts with.

```mermaid
C4Context
    title System Context Diagram — TelegramAIAgent (Module 3)

    Person(ops_manager, "Gerente de Operaciones", "Recibe alertas y puede solicitar verificaciones manuales via Telegram")

    System(telegram_agent, "TelegramAIAgent", "Agente inteligente que transforma alertas del motor de decisión en mensajes narrativos para Telegram usando un LLM")

    System_Ext(early_alerts_api, "EarlyAlertsAPI (Module 2)", "Motor de decisión que evalúa pronósticos meteorológicos y emite alertas a un outbox con recomendaciones de earnings")
    System_Ext(telegram_api, "Telegram Bot API", "Plataforma de mensajería para comunicación directa con el Gerente de Operaciones")
    System_Ext(llm_provider, "LLM Provider", "Proveedor de modelos de lenguaje (OpenAI GPT-4o-mini, Anthropic, Ollama, etc.) via LiteLLM")
    System_Ext(weather_api, "Open-Meteo API", "API de pronósticos meteorológicos consumida por EarlyAlertsAPI (no directamente por Module 3)")

    Rel(ops_manager, telegram_agent, "Envía comandos /check, /force_check, /status", "Telegram Bot")
    Rel(telegram_agent, ops_manager, "Envía alertas narrativas de riesgo", "Telegram Bot")

    Rel(telegram_agent, early_alerts_api, "Consulta alertas pendientes, marca consumidas, dispara ciclos", "HTTP/REST")
    Rel(telegram_agent, telegram_api, "Envía mensajes de alerta", "HTTPS")
    Rel(telegram_agent, llm_provider, "Genera narración de alertas", "HTTPS (LiteLLM)")

    Rel(weather_api, early_alerts_api, "Provee pronósticos horarios", "HTTPS")
```

## Descripción

| Elemento | Rol |
|---|---|
| **Gerente de Operaciones** | Usuario final. Recibe notificaciones push de alertas y puede interactuar manualmente con el bot. |
| **TelegramAIAgent** | El sistema bajo análisis. Orquesta la transformación de alertas crudas del motor en mensajes Telegram enriquecidos, usando un LLM para generación de texto natural. |
| **EarlyAlertsAPI** | Sistema externo (Module 2). Produce las alertas en su outbox (zona, nivel de riesgo, precipitación, earnings recomendados, etc.). |
| **Telegram Bot API** | Canal de comunicación con el usuario final. |
| **LLM Provider** | Servicio externo de IA generativa. Configurable via LiteLLM (OpenAI, Anthropic, Ollama, Azure). |
| **Open-Meteo API** | Fuente de datos meteorológicos — consumida por Module 2, no directamente por Module 3. |
