"""System prompt builder and per-alert user message formatter."""
from __future__ import annotations

_SYSTEM_PROMPT_TEMPLATE = """\
Eres un asistente de alertas operativas para la flota de repartidores de Rappi en Monterrey.
Tu único trabajo es redactar mensajes de alerta para el Gerente de Operaciones en Telegram.

REGLAS ESTRICTAS:
1. El mensaje DEBE tener exactamente estas 5 secciones en orden:
   🚨 ZONA + NIVEL DE RIESGO (una línea)
   📊 QUÉ SE ESPERA (2-3 líneas: qué pasará y por qué, usando números del historial)
   💰 ACCIÓN (una línea concreta: cuánto subir los earnings y en cuántos minutos)
   ⏱️ VENTANA (una línea: cuánto tiempo hay para actuar)
   📍 ZONAS SECUNDARIAS (una línea: zonas a monitorear, o "Ninguna" si no hay)

2. Idioma: español. Tono: directo, sin saludos ni despedidas.
3. Legible en 10 segundos. Sin Markdown (asteriscos, guiones, viñetas especiales).
4. Los números deben ser específicos y coincidir exactamente con los datos proporcionados.
5. Nivel de riesgo: usa BAJO / MEDIO / ALTO / CRÍTICO (nunca otros términos).

REGLAS DEL MOTOR Y CONTEXTO HISTÓRICO CALIBRADO (Módulo 2 — Monterrey):
---
{motor_context}
---

Usa estas reglas y sus estadísticas de calibración para enriquecer la sección
"Qué se espera" con números específicos (ratios, % de saturación, earnings históricos).
Todos los valores del alert payload ya fueron computados por el motor usando estas reglas.
"""

_USER_MESSAGE_TEMPLATE = """\
Alerta del motor de decisión:
- Zona: {zone}
- Nivel de riesgo: {risk_display}
- Precipitación pronosticada: {precip_mm} mm/hr
- Ratio proyectado: {projected_ratio:.2f}
- Earnings actual (baseline): 55.6 MXN
- Earnings recomendado: {recommended_earnings_mxn:.1f} MXN (+{uplift_mxn:.1f} MXN)
- Ventana para actuar: {lead_time_min} minutos
- Zonas secundarias: {secondary_zones_str}
- Razón del motor: {reason}
- Hora del forecast: {forecast_time}
"""

_RISK_DISPLAY_MAP = {
    "medio": "MEDIO",
    "alto": "ALTO",
    "critico": "CRÍTICO",
}


def build_system_prompt(motor_context: str) -> str:
    """Construct the full system prompt with injected Motor rule context."""
    return _SYSTEM_PROMPT_TEMPLATE.format(motor_context=motor_context)


def map_risk_display(risk_level: str) -> str:
    """Map engine risk_level strings to display labels (adds BAJO for null case)."""
    return _RISK_DISPLAY_MAP.get(risk_level.lower(), risk_level.upper())


def build_user_message(alert: dict, risk_display: str) -> str:
    """Build the per-alert user message from the alert payload.

    All decisions (projected_ratio, earnings, risk_level, secondary_zones) are
    already computed by EarlyAlertsAPI using calibrated rules. The LLM uses the
    Motor context in the system prompt to narrate the "why" behind these numbers.
    """
    secondary = alert.get("secondary_zones") or []
    secondary_zones_str = ", ".join(secondary) if secondary else "Ninguna"

    return _USER_MESSAGE_TEMPLATE.format(
        zone=alert.get("zone", ""),
        risk_display=risk_display,
        precip_mm=float(alert.get("precip_mm", 0)),
        projected_ratio=float(alert.get("projected_ratio", 0)),
        recommended_earnings_mxn=float(alert.get("recommended_earnings_mxn", 0)),
        uplift_mxn=float(alert.get("uplift_mxn", 0)),
        lead_time_min=alert.get("lead_time_min", 0),
        secondary_zones_str=secondary_zones_str,
        reason=alert.get("reason", ""),
        forecast_time=alert.get("forecast_time", ""),
    )
