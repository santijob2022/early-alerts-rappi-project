"""TelegramAIAgent entrypoint.

Starts two concurrent tasks:
1. Auto poll loop — every poll_interval_seconds, fetches pending alerts and
   processes each through the pipeline (orchestrator → Telegram → ack).
2. Telegram command listener — handles /check, /force_check, /status.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from app.agent.context_source import ContextSourceService
from app.agent.llm.client import LLMClient
from app.agent.orchestrator import AlertOrchestrator
from app.agent.prompts.system_prompt import build_system_prompt
from app.config import Settings
from app.services.alerts_api.consumer import AlertsAPIConsumer
from app.services.telegram.commands import build_application
from app.services.telegram.sender import send_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def poll_loop(
    settings: Settings,
    consumer: AlertsAPIConsumer,
    orchestrator: AlertOrchestrator,
) -> None:
    """Continuously poll for pending alerts and process them."""
    logger.info("Poll loop started (interval: %ss)", settings.poll_interval_seconds)
    while True:
        try:
            alerts = await consumer.fetch_pending_alerts()
            if alerts:
                logger.info("Found %d pending alert(s). Processing...", len(alerts))
            for alert in alerts:
                try:
                    text = await orchestrator.process_alert(alert)
                    sent = await send_message(settings.telegram_bot_token, settings.telegram_chat_id, text)
                    if sent:
                        await consumer.mark_consumed(alert["id"])
                        logger.info("Alert %s sent and consumed.", alert["id"])
                    else:
                        logger.warning("Telegram send failed for alert %s — will retry next cycle.", alert["id"])
                except Exception:
                    logger.exception("Error processing alert %s — skipping.", alert.get("id"))
        except Exception:
            logger.exception("Error in poll loop iteration — will retry.")
        await asyncio.sleep(settings.poll_interval_seconds)


async def main() -> None:
    settings = Settings()
    logger.info("Starting TelegramAIAgent (model: %s)", settings.llm_model)

    # ── Instantiate services ──────────────────────────────────────────────────
    context_service = ContextSourceService(settings)
    llm_client = LLMClient(settings)
    consumer = AlertsAPIConsumer(settings.alerts_api_base_url)
    system_prompt = build_system_prompt(context_service.get_motor_context())
    orchestrator = AlertOrchestrator(context_service, llm_client, system_prompt)

    # ── Telegram command application ──────────────────────────────────────────
    tg_app = build_application(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        consumer=consumer,
        orchestrator=orchestrator,
        display_timezone=settings.display_timezone,
    )

    # ── Run both concurrently ─────────────────────────────────────────────────
    async with tg_app:
        await tg_app.initialize()
        await tg_app.start()
        await tg_app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram command listener started.")

        try:
            await poll_loop(settings, consumer, orchestrator)
        finally:
            await tg_app.updater.stop()
            await tg_app.stop()
            await tg_app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
