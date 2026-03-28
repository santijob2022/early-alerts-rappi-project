"""Telegram Bot command handlers: /check, /force_check, /status.

Each command handler runs the same alert pipeline as the auto poll loop.
/check   — fetch pending alerts and process them; if none, report BAJO.
/force_check — trigger a fresh engine cycle first, then process any alerts.
/status  — report EarlyAlertsAPI health (last_run, open events).
"""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from app.agent.orchestrator import AlertOrchestrator
from app.services.alerts_api.consumer import AlertsAPIConsumer
from app.services.telegram.sender import send_message

logger = logging.getLogger(__name__)


def _fmt_baixo_response(health: dict, display_timezone: str) -> str:
    raw_last_run = health.get("last_run")
    last_run = _fmt_datetime(raw_last_run, display_timezone) if raw_last_run else "desconocido"
    open_events = health.get("open_events", 0)
    return (
        "✅ Sin riesgo inminente — Nivel: BAJO\n\n"
        f"Última ejecución del motor: {last_run}\n"
        f"Eventos abiertos: {open_events}"
    )


async def _process_and_send(
    update: Update,
    alerts: list[dict],
    health: dict,
    orchestrator: AlertOrchestrator,
    consumer: AlertsAPIConsumer,
    bot_token: str,
    chat_id: str,
    display_timezone: str,
) -> None:
    if not alerts:
        msg = _fmt_baixo_response(health, display_timezone)
        await update.message.reply_text(msg)
        return

    for alert in alerts:
        try:
            text = await orchestrator.process_alert(alert)
            sent = await send_message(bot_token, chat_id, text)
            if sent:
                await consumer.mark_consumed(alert["id"])
                logger.info("Alert %s sent and consumed via /command", alert["id"])
        except Exception:
            logger.exception("Failed to process alert %s in command handler", alert.get("id"))
            await update.message.reply_text(
                f"⚠️ Error procesando alerta {alert.get('id')} — revisa los logs."
            )


def _fmt_datetime(raw: str, tz_name: str) -> str:
    """Parse an ISO datetime string and format it using the given IANA timezone."""
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
    try:
        dt = datetime.fromisoformat(raw).astimezone(tz)
        tz_abbr = dt.strftime("%Z")
        return dt.strftime(f"%d %b %Y, %H:%M {tz_abbr}")
    except ValueError:
        return raw


def build_application(
    bot_token: str,
    chat_id: str,
    consumer: AlertsAPIConsumer,
    orchestrator: AlertOrchestrator,
    display_timezone: str = "America/Mexico_City",
) -> Application:
    """Build and return a configured python-telegram-bot Application."""
    app = Application.builder().token(bot_token).build()

    async def check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/check — fetch pending alerts; report BAJO if none."""
        await update.message.reply_text("🔍 Consultando alertas pendientes...")
        try:
            alerts = await consumer.fetch_pending_alerts()
            health = await consumer.get_health()
        except Exception as exc:
            logger.exception("Error fetching alerts for /check")
            await update.message.reply_text(f"❌ Error al consultar EarlyAlertsAPI: {exc}")
            return
        await _process_and_send(update, alerts, health, orchestrator, consumer, bot_token, chat_id, display_timezone)

    async def force_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/force_check — trigger run-once, then fetch and process alerts."""
        await update.message.reply_text("⚡ Ejecutando ciclo de evaluación...")
        try:
            run_result = await consumer.trigger_run_once()
            emitted = run_result.get("alerts_emitted", 0)
            await update.message.reply_text(
                f"Motor ejecutado. Alertas emitidas: {emitted}. Procesando..."
            )
            alerts = await consumer.fetch_pending_alerts()
            health = await consumer.get_health()
        except Exception as exc:
            logger.exception("Error during /force_check")
            await update.message.reply_text(f"❌ Error: {exc}")
            return
        await _process_and_send(update, alerts, health, orchestrator, consumer, bot_token, chat_id, display_timezone)

    async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/status — report EarlyAlertsAPI health."""
        try:
            health = await consumer.get_health()
        except Exception as exc:
            logger.exception("Error fetching health for /status")
            await update.message.reply_text(f"❌ No se puede contactar EarlyAlertsAPI: {exc}")
            return
        raw_last_run = health.get("last_run")
        last_run = _fmt_datetime(raw_last_run, display_timezone) if raw_last_run else "nunca"
        open_events = health.get("open_events", "?")
        status_flag = health.get("status", "?")
        await update.message.reply_text(
            f"📡 Estado del Motor\n\n"
            f"Estado: {status_flag}\n"
            f"Última ejecución: {last_run}\n"
            f"Eventos abiertos: {open_events}"
        )

    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("force_check", force_check))
    app.add_handler(CommandHandler("status", status))

    return app
