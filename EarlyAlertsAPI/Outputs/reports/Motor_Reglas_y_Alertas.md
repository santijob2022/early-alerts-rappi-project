# Motor de Reglas y Alertas - Modulo 2b

## Objetivo

Definir un motor de decision que convierta el forecast horario de precipitacion en alertas accionables para Operations. La regla no debe ser generica: debe estar calibrada con el historico del Modulo 1 para responder cuatro preguntas de negocio:

1. Que umbral de lluvia dispara una alerta y si cambia por zona.
2. Con cuanta anticipacion conviene actuar.
3. A cuanto debe subir el earnings recomendado.
4. Como evitar alertas duplicadas por el mismo evento.

El motor se disena para alimentar el script de 2c y, mas adelante, los mensajes de Telegram del Modulo 3.

## Fuentes de evidencia y trazabilidad

Etiquetas usadas en este documento:

- `[M1-P1]`: hallazgos de saturacion por hora y zona del Modulo 1.
- `[M1-P2]`: hallazgos de lluvia vs `RATIO` del Modulo 1.
- `[M1-P3]`: sensibilidad por zona a la lluvia del Modulo 1.
- `[M1-P5]`: interaccion entre earnings, lluvia y saturacion del Modulo 1.
- `[CALC-1]`: notebook complementario [01_alert_rules_motor_calibration.ipynb](EarlyAlertsAPI/notebooks/01_alert_rules_motor_calibration.ipynb), construido sobre el mismo dataset limpio para fijar thresholds, lead time, target de earnings, duracion de eventos y proximidad entre zonas.

## Hallazgos historicos que fijan las reglas

Los numeros que gobiernan el motor salen del analisis de `DataAnalysis`:

- Las ventanas mas fragiles son lunch `12:00-14:00` y dinner `19:00-21:00`. A nivel ciudad, `14:00` satura en `27.9%` de las observaciones, `13:00` en `26.0%`, `12:00` en `24.5%`, y dinner agrega un segundo bloque de riesgo en `19:00-21:00`. [M1-P1]
- La lluvia es el principal estresor operativo. El `RATIO` promedio sube de `0.775` en `no_rain` a `1.700` en `moderate` y `1.769` en `heavy`; la saturacion pasa de `3.7%` a `31.2%-33.9%`. [M1-P2]
- En peak hours, el salto operativo es aun mas claro: con `forecast >= 2.0 mm/hr`, el `RATIO` promedio llega a `1.992` y `47.1%` de las horas quedan saturadas. [CALC-1]
- Las zonas mas sensibles por deterioro relativo son `Santiago` (`+1.821`), `Carretera Nacional` (`+1.484`), `MTY_Apodaca_Huinala` (`+1.061`) y `Santa Catarina` (`+0.991`). [M1-P3]
- Para lluvia de `>= 1.0 mm/hr` en peak hours, esas zonas ya muestran riesgo alto: `Santiago` proyecta `RATIO 2.700`, `Carretera Nacional 2.407`, `Santa Catarina 2.171` y `MTY_Apodaca_Huinala 2.120`. [CALC-1]
- El efecto de earnings no es util en agregado, pero si bajo lluvia. En `moderate/heavy`, el cuartil alto de earnings reduce fuerte la saturacion: en lluvia peak, el objetivo historico equivalente es `80.3 MXN` de mediana y `79.5 MXN` de media. [M1-P5][CALC-1]
- Los eventos `moderate+` duran mediana `4h` y maximo observado `6h`, por lo que la memoria del motor debe agrupar varias horas consecutivas en un solo evento. [CALC-1]

## Regla 1 - Umbral de precipitacion que dispara la alerta

### Regla base

- Umbral estandar de alerta: `forecast t+1 >= 2.0 mm/hr`. [M1-P2][CALC-1]
- Justificacion: `2.0 mm/hr` es el punto en el que el historico deja de comportarse como ruido de lluvia ligera y entra en el regimen operativo de `moderate/heavy`, donde el `RATIO` promedio se mueve cerca de saturacion y la tasa de horas saturadas sube de forma material. [M1-P2][CALC-1]
- No usar `5.0 mm/hr` como trigger primario. Debe usarse solo para escalar severidad porque agrega poca senal incremental frente a `2.0 mm/hr` y sacrifica ventana de reaccion. [CALC-1]

### Regla diferenciada por zona

Solo las zonas con sensibilidad estructural alta reciben un trigger mas agresivo:

- `Santiago`
- `Carretera Nacional`
- `Santa Catarina`
- `MTY_Apodaca_Huinala`

Para ellas, si la hora forecast cae en lunch o dinner, el trigger baja a `forecast t+1 >= 1.0 mm/hr`. [M1-P3][CALC-1]

### Regla de trigger final

- Si `zone` es sensible y `forecast_hour` esta en `{12,13,14,19,20,21}`, usar `trigger_mm = 1.0`. [M1-P3][CALC-1]
- En cualquier otro caso, usar `trigger_mm = 2.0`. [M1-P2][CALC-1]
- Si `forecast_precip_mm >= 5.0`, mantener el mismo evento pero escalar `risk_level` a `critico` si el caso ya era notificable. [M1-P2][CALC-1]

## Regla 2 - Anticipacion: forecast 1h vs 3h

### Horizonte principal

- Horizonte principal de alerta: `1h`. [CALC-1]
- Horizonte secundario: `3h` solo como watchlist silenciosa. [CALC-1]

### Justificacion

En peak hours, cuando hoy vemos lluvia `>= 2.0 mm/hr`:

- same-hour: `47.1%` de saturacion [CALC-1]
- `+1h`: `26.1%` [CALC-1]
- `+2h`: `8.4%` [CALC-1]
- `+3h`: `1.7%` [CALC-1]

La lectura operativa es clara:

- `1h` da una ventana accionable sin diluir demasiado la precision. [CALC-1]
- `3h` ya no justifica una notificacion activa; sirve para pre-posicionar observacion, no para disparar Telegram. [CALC-1]

### Politica de uso

- `t+1` puede generar `alert`, `escalate` o `suppress`. [CALC-1]
- `t+2` y `t+3` solo pueden generar `watch`. [CALC-1]
- Si existe riesgo a `t+3` pero `t+1` sigue bajo trigger, el motor debe guardar el caso en watchlist interna y no enviar Telegram. [CALC-1]

## Regla 3 - Earnings recomendado

### Target operativo

- Target unico recomendado por el motor: `80 MXN/order`. [M1-P5][CALC-1]

### Justificacion

- En lluvia peak `moderate+`, el historico vigente tiene `70.5 MXN` de mediana. [CALC-1]
- El cuartil alto en esas mismas condiciones tiene `80.3 MXN` de mediana y `79.5 MXN` de media. [M1-P5][CALC-1]
- Redondear a `80 MXN` mantiene la regla simple, defendible y estable para Telegram. [CALC-1]

### Como expresar el uplift

El documento y los mensajes de 2c deben usar dos referencias distintas:

- Contra baseline ciudad: `55.6 -> 80 MXN` (`+24.4 MXN`). [CALC-1]
- Contra rainy peak vigente: `70.5 -> 80 MXN` (`+9.8 MXN`). [CALC-1]

### Regla operativa

- Si `current_earnings_mxn < 80`, recomendar `recommended_earnings_mxn = 80`. [CALC-1]
- Si `current_earnings_mxn >= 80`, recomendar `recommended_earnings_mxn = current_earnings_mxn` y `uplift_mxn = 0`. [CALC-1]
- No usar targets por zona en la regla final. Aunque existen diferencias, las celdas `rainy x Q4` por zona son pequenas (`n=9-14`) y el analisis del notebook recomienda evitar sobreajuste. [M1-P5][CALC-1]
- El Modulo 2 busca prevenir saturacion, no optimizar overspend a la baja durante una tormenta activa. Por eso el motor no recomienda bajar earnings dentro de un evento de lluvia.

## Regla 4 - Calculo de riesgo y projected ratio

El `projected_ratio` debe salir de un lookup historico, no de una formula arbitraria entrenada sobre un dataset pequeno.

### Fuente del baseline

1. Tomar `baseline_no_rain_ratio(zone, forecast_hour)` usando solo horas historicas con `PRECIPITATION_MM < 0.1`. [CALC-1]
2. Si ese `zone x hour` tiene muestra insuficiente, usar `baseline_no_rain_ratio(zone, hour_window)` donde `hour_window` es `peak` u `offpeak`. [CALC-1]
3. Si aun asi falta muestra, usar `avg_ratio_no_rain` de la zona. [M1-P3][CALC-1]

### Lifts de lluvia a sumar sobre el baseline

Usar lifts fijos calibrados desde el historico:

#### Peak hours (`12:00-14:00`, `19:00-21:00`)

- `0.1-1.9 mm/hr`: `+0.29` [CALC-1]
- `2.0-4.9 mm/hr`: `+0.60` [CALC-1]
- `>= 5.0 mm/hr`: `+0.60` [CALC-1]

Estos lifts salen de comparar el baseline seco peak (`1.388`) contra el efecto agregado en lluvia para no sobrerreaccionar en zonas no sensibles. La lluvia pesada no agrega mucho mas `RATIO` que la moderada en el historico peak, por eso el salto adicional se expresa via severidad y no via un uplift mucho mayor. [CALC-1]

#### Off-peak

- `0.1-1.9 mm/hr`: `+0.29` [CALC-1]
- `2.0-4.9 mm/hr`: `+0.97` [CALC-1]
- `>= 5.0 mm/hr`: `+0.99` [CALC-1]

Estos lifts salen del efecto agregado all-hours (`0.775 -> 1.060 -> 1.741 -> 1.769`) y se usan porque la muestra lluviosa fuera de peak es mas escasa. [M1-P2][CALC-1]

### Override de zonas sensibles

Para evitar perder eventos tempranos en zonas fragiles, si la zona es sensible, la hora es peak y `1.0 <= forecast_precip_mm < 2.0`, aplicar un piso de `projected_ratio` por zona:

- `Santiago`: `2.700` [CALC-1]
- `Carretera Nacional`: `2.407` [CALC-1]
- `Santa Catarina`: `2.171` [CALC-1]
- `MTY_Apodaca_Huinala`: `2.120` [CALC-1]

La regla es:

`projected_ratio = max(baseline + rain_lift, sensitive_peak_floor[zone])` [CALC-1]

### Severidad

- `medio`: `1.50-1.79` [CALC-1]
- `alto`: `1.80-2.19` [CALC-1]
- `critico`: `>= 2.20` [CALC-1]

Adicionalmente:

- Si `forecast_precip_mm >= 5.0` y el caso ya es notificable, subir a `critico`. [M1-P2][CALC-1]
- Telegram solo sale para `alto` y `critico`. [CALC-1]
- Excepcion: si el caso viene del override sensible `1.0-1.9 mm/hr` en peak, se permite Telegram aunque el caso quede etiquetado como `medio`, para no perder eventos tempranos en esas cuatro zonas. En la practica, con los pisos historicos, la mayoria de esos casos ya cae en `alto/critico`. [CALC-1]

## Regla 5 - Como elegir zonas secundarias a monitorear

La recomendacion no debe ser manual. Debe ser reproducible.

### Ranking

1. Tomar solo zonas con lluvia inminente en la misma ventana (`t+1 >= 1.0 mm/hr` para watch o `>= trigger_mm` para alerta). [CALC-1]
2. Ordenar primero por vulnerabilidad estructural:
   - sensibles: `Santiago`, `Carretera Nacional`, `Santa Catarina`, `MTY_Apodaca_Huinala` [M1-P3]
   - monitores de volumen: `Centro`, `San Pedro`, `MTY_Guadalupe`, `San Nicolas` [M1-P3]
3. Romper empates por `forecast_precip_mm` descendente. [CALC-1]
4. Si aun hay empate, usar distancia entre centroides desde `ZONE_INFO` y priorizar las mas cercanas. [CALC-1]
5. Devolver maximo dos zonas secundarias. [CALC-1]

### Fallback de proximidad

Si no hay otra zona con trigger claro, usar los centroides mas cercanos de la zona principal:

- `Santiago` -> `Carretera Nacional`, `MTY_Guadalupe` [CALC-1]
- `Carretera Nacional` -> `MTY_Guadalupe`, `Independencia` [CALC-1]
- `Santa Catarina` -> `San Pedro`, `Cumbres Poniente` [CALC-1]
- `MTY_Apodaca_Huinala` -> `MTY_Guadalupe`, `Apodaca Centro` [CALC-1]

## Regla 6 - Como evitar alertas duplicadas

El motor debe mantener memoria por `zona-evento`.

### Contrato de memoria

`AlertMemory = {zone, event_id, opened_at, last_sent_at, max_risk, max_precip_mm, status}` [CALC-1]

### Politica de evento

- Abrir un evento cuando una zona cruza su `trigger_mm` en `t+1` y no existe un evento activo. [CALC-1]
- Mantener el mismo `event_id` mientras la zona siga por encima del trigger o no acumule `2` horas consecutivas por debajo de `0.1 mm/hr` o por debajo del trigger activo. [CALC-1]
- Cerrar el evento solo cuando se cumpla esa condicion de `2` horas consecutivas de alivio. [CALC-1]

### Cooldown

- Cooldown por evento-zona: `4h`. [CALC-1]
- Justificacion: los eventos `moderate+` duran mediana `4h` y maximo `6h`, asi que mandar una alerta cada hora reintroduce ruido. [CALC-1]

### Cuando reenviar

Solo reenviar dentro del mismo evento si pasa al menos una de estas condiciones:

- `risk_level` sube. [CALC-1]
- `forecast_precip_mm` sube `>= 1.0 mm/hr` contra el ultimo snapshot enviado. [CALC-1]
- `recommended_earnings_mxn` cambia `>= 5 MXN`. [CALC-1]

Si no ocurre ninguna, la decision debe ser `suppress`.

## Interfaces para 2c

### DecisionInput

`DecisionInput = {zone, forecast_hour, forecast_precip_mm, current_hour, current_earnings_mxn}`

Interpretacion:

- `forecast_hour`: hora local Monterrey del bucket forecast evaluado.
- `current_hour`: hora local en la que corre el script.
- Para produccion conviene anexar timestamp completo, pero este es el contrato minimo que 2c necesita para implementar la logica.

### DecisionOutput

`DecisionOutput = {trigger_state, risk_level, projected_ratio, recommended_earnings_mxn, uplift_mxn, lead_time_min, secondary_zones, reason}`

Campos:

- `trigger_state`: `watch`, `alert`, `escalate` o `suppress`
- `risk_level`: `medio`, `alto`, `critico`
- `projected_ratio`: lookup historico ajustado por lluvia
- `recommended_earnings_mxn`: target final sugerido
- `uplift_mxn`: `recommended_earnings_mxn - current_earnings_mxn`, con piso en `0`
- `lead_time_min`: `60`, `120` o `180`
- `secondary_zones`: lista de hasta dos zonas
- `reason`: explicacion breve y trazable

## Pseudocodigo de referencia

```text
PEAK_HOURS = {12, 13, 14, 19, 20, 21}
SENSITIVE_ZONES = {"Santiago", "Carretera Nacional", "Santa Catarina", "MTY_Apodaca_Huinala"}
VOLUME_MONITORS = {"Centro", "San Pedro", "MTY_Guadalupe", "San Nicolas"}
SENSITIVE_PEAK_FLOOR = {
  "Santiago": 2.700,
  "Carretera Nacional": 2.407,
  "Santa Catarina": 2.171,
  "MTY_Apodaca_Huinala": 2.120,
}
RAIN_LIFT_PEAK = {"light": 0.29, "moderate": 0.60, "heavy": 0.60}
RAIN_LIFT_OFFPEAK = {"light": 0.29, "moderate": 0.97, "heavy": 0.99}
TARGET_EARNINGS = 80.0
COOLDOWN_HOURS = 4
CLOSE_STREAK_HOURS = 2

def bucketize_rain(mm):
    if mm < 0.1: return "dry"
    if mm < 2.0: return "light"
    if mm < 5.0: return "moderate"
    return "heavy"

def decide_alert(input, memory, forecast_context):
    is_peak = input.forecast_hour in PEAK_HOURS
    is_sensitive = input.zone in SENSITIVE_ZONES
    lead_time_min = ((input.forecast_hour - input.current_hour) % 24) * 60
    rain_bucket = bucketize_rain(input.forecast_precip_mm)
    trigger_mm = 1.0 if is_peak and is_sensitive else 2.0

    if lead_time_min == 0:
        lead_time_min = 60

    if lead_time_min > 60:
        if input.forecast_precip_mm >= trigger_mm:
            return watch(reason="riesgo a mas de 1h; mantener monitoreo silencioso")
        return suppress(reason="sin riesgo inmediato")

    if input.forecast_precip_mm < 0.1:
        update_memory_dry_streak(memory, input.zone)
        return suppress(reason="sin lluvia")

    baseline = lookup_no_rain_ratio(input.zone, input.forecast_hour)

    if is_peak:
        rain_lift = RAIN_LIFT_PEAK[rain_bucket]
    else:
        rain_lift = RAIN_LIFT_OFFPEAK[rain_bucket]

    projected_ratio = baseline + rain_lift

    if is_peak and is_sensitive and 1.0 <= input.forecast_precip_mm < 2.0:
        projected_ratio = max(projected_ratio, SENSITIVE_PEAK_FLOOR[input.zone])

    risk_level = classify(projected_ratio)

    if input.forecast_precip_mm >= 5.0 and projected_ratio >= 1.8:
        risk_level = "critico"

    recommended_earnings_mxn = max(input.current_earnings_mxn, TARGET_EARNINGS)
    uplift_mxn = max(0, recommended_earnings_mxn - input.current_earnings_mxn)

    if input.forecast_precip_mm < trigger_mm:
        return watch(
            risk_level=risk_level,
            projected_ratio=projected_ratio,
            recommended_earnings_mxn=recommended_earnings_mxn,
            uplift_mxn=uplift_mxn,
            reason="lluvia ligera fuera del trigger; solo watchlist"
        )

    if risk_level == "medio" and not (is_peak and is_sensitive):
        return watch(reason="riesgo medio sin override sensible")

    secondary_zones = rank_secondary_zones(input.zone, forecast_context)

    if should_suppress_by_memory(memory, input.zone, risk_level, input.forecast_precip_mm, recommended_earnings_mxn):
        return suppress(reason="mismo evento dentro del cooldown")

    trigger_state = "escalate" if event_exists_and_worsens(memory, input.zone, risk_level, input.forecast_precip_mm, recommended_earnings_mxn) else "alert"

    save_or_refresh_event(memory, input.zone, risk_level, input.forecast_precip_mm, recommended_earnings_mxn)

    return {
      trigger_state,
      risk_level,
      projected_ratio,
      recommended_earnings_mxn,
      uplift_mxn,
      lead_time_min,
      secondary_zones,
      reason=build_reason(...)
    }
```

## Escenarios que 2c debe pasar

### Escenario 1

- Input: `Santiago`, `13:00`, `1.2 mm/hr`, `current_earnings = 70`
- Esperado: `alert`
- Justificacion: zona sensible + peak hour + override `1.0 mm/hr`; `projected_ratio` debe respetar piso `2.700`; recomendacion `80 MXN`

### Escenario 2

- Input: `Centro`, `13:00`, `1.2 mm/hr`, `current_earnings = 70`
- Esperado: `watch`
- Justificacion: zona no sensible, no cruza el trigger estandar `2.0 mm/hr`; mantener monitoreo silencioso para evitar alert fatigue

### Escenario 3

- Input: `Centro`, `14:00`, `2.5 mm/hr`, `current_earnings = 72`
- Esperado: `alert` con riesgo `alto`
- Justificacion: en peak hours, el lift `moderate` sobre baseline seco de `Centro` lleva el `projected_ratio` a rango de saturacion notificable

### Escenario 4

- Input: misma tormenta en la misma zona durante 3 horas seguidas
- Esperado: una sola alerta inicial y luego `suppress`, salvo escalamiento real
- Justificacion: `4h` de cooldown por evento-zona

### Escenario 5

- Input: `t+3 = 3.0 mm/hr`, pero `t+1 < 2.0 mm/hr`
- Esperado: `watch`, sin Telegram
- Justificacion: `3h` es watchlist silenciosa, no notificacion

## Trazabilidad detallada de fuentes

- `[M1-P1]`: [03_kpis_and_findings.ipynb](DataAnalysis/notebooks/03_kpis_and_findings.ipynb), seccion P1; soporte tambien en [resumen_hallazgos_modulo1_1_pagina.md](DataAnalysis/outputs/reports/resumen_hallazgos_modulo1_1_pagina.md) y en `DataAnalysis/outputs/tables/p1_hour_saturation_frequency.csv`.
- `[M1-P2]`: [03_kpis_and_findings.ipynb](DataAnalysis/notebooks/03_kpis_and_findings.ipynb), seccion P2; tablas `DataAnalysis/outputs/tables/p2_rain_bucket_ratio.csv` y `DataAnalysis/outputs/tables/p2_hour_control_ratio_lift.csv`.
- `[M1-P3]`: [03_kpis_and_findings.ipynb](DataAnalysis/notebooks/03_kpis_and_findings.ipynb), seccion P3; tabla `DataAnalysis/outputs/tables/p3_zone_precipitation_sensitivity.csv`.
- `[M1-P5]`: [03_kpis_and_findings.ipynb](DataAnalysis/notebooks/03_kpis_and_findings.ipynb), seccion P5; tabla `DataAnalysis/outputs/tables/p5_earnings_rain_ratio_interaction.csv`.
- `[CALC-1]`: [01_alert_rules_motor_calibration.ipynb](EarlyAlertsAPI/notebooks/01_alert_rules_motor_calibration.ipynb), con calculos complementarios sobre `DataAnalysis/outputs/cleaned/raw_data_clean.parquet` y `DataAnalysis/outputs/cleaned/zone_info_clean.parquet`.

## Resultado esperado para 2c

Con estas reglas, el script funcional de 2c debe poder producir mensajes del tipo:

- zona afectada
- lluvia esperada y lead time
- `projected_ratio` basado en historico
- recomendacion puntual de earnings hasta `80 MXN`
- una o dos zonas secundarias trazables

La clave es que el mensaje salga de reglas simples, numericas y auditables, no de intuicion manual.
