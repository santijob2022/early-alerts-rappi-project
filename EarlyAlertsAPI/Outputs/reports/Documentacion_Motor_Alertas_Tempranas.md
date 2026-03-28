# Documentacion del Motor de Alertas Tempranas - Modulo 2

## Fuentes y trazabilidad

Etiquetas usadas en este reporte:

- `[M1-P1]`: saturacion por hora y zona del Modulo 1.
- `[M1-P2]`: lluvia vs `RATIO` del Modulo 1.
- `[M1-P3]`: sensibilidad por zona del Modulo 1.
- `[M1-P5]`: earnings vs lluvia/saturacion del Modulo 1.
- `[CALC-1]`: notebook complementario [01_alert_rules_motor_calibration.ipynb](EarlyAlertsAPI/notebooks/01_alert_rules_motor_calibration.ipynb) con calculos adicionales sobre el parquet limpio.

## 2a. API climatica y mapeo de zonas

- Se elige **Open-Meteo** porque entrega `precipitation` en `mm/hr`, el mismo formato del dataset historico; no requiere API key y devuelve forecast horario suficiente para comparar `1h` vs `3h`. [M1-P2]
- Para el prototipo basta consultar el forecast por los centroides de `ZONE_INFO`; si se quiere mas precision, se puede muestrear una malla de coordenadas y asignarlas a `ZONE_POLYGONS` con `point-in-polygon`. [CALC-1]
- El pipeline debe normalizar todo a hora local Monterrey y convertir cada forecast en una observacion `zona x hora`, que es el mismo grano del Modulo 1. [M1-P1]

## 2b. Reglas del motor justificadas con historico

### 1. Umbral de lluvia que dispara alerta

- Regla base: `forecast t+1 >= 2.0 mm/hr`. [M1-P2][CALC-1]
- Justificacion: ahi empieza el regimen `moderate/heavy` del historico, donde el `RATIO` sube de `0.775` en seco a `1.700-1.769`, y la saturacion pasa de `3.7%` a `31.2%-33.9%`. [M1-P2]
- En lunch/dinner (`12:00-14:00`, `19:00-21:00`) la senal es aun mas fuerte: con `>= 2.0 mm/hr`, el `RATIO` promedio llega a `1.992` y `47.1%` de las horas quedan saturadas. [CALC-1]
- Excepcion por zona: `Santiago`, `Carretera Nacional`, `Santa Catarina` y `MTY_Apodaca_Huinala` disparan antes, con `forecast t+1 >= 1.0 mm/hr` solo en peak hours, porque ya muestran `RATIO` de `2.12-2.70` y `47%-68%` de saturacion en ese rango. [M1-P3][CALC-1]
- `>= 5.0 mm/hr` no se usa como primer trigger; se usa solo para escalar severidad a `critico`. [M1-P2][CALC-1]

### 2. Cuanta anticipacion usar

- Horizonte principal: `1h`. [CALC-1]
- Horizonte secundario: `3h` solo como watchlist silenciosa. [CALC-1]
- Justificacion: en peak hours, con lluvia `>= 2.0 mm/hr`, la saturacion cae de `47.1%` same-hour a `26.1%` en `+1h`, `8.4%` en `+2h` y `1.7%` en `+3h`. [CALC-1]
- Lectura operativa: `1h` todavia conserva precision y deja tiempo para reaccionar; `3h` sirve para monitoreo interno, no para Telegram. [CALC-1]

### 3. Cuanto subir earnings

- Target unico del motor: **`80 MXN/order`**. [M1-P5][CALC-1]
- Justificacion: en lluvia peak `moderate+`, el historico vigente tiene `70.5 MXN` de mediana, mientras el cuartil alto asociado a mejor desempeno llega a `80.3 MXN` de mediana y `79.5 MXN` de media. [M1-P5][CALC-1]
- Como defenderlo:
  - contra baseline ciudad: `55.6 -> 80 MXN` (`+24.4 MXN`) [CALC-1]
  - contra rainy peak vigente: `70.5 -> 80 MXN` (`+9.8 MXN`) [CALC-1]
- No se usan targets por zona porque las celdas lluviosas de `Q4` por zona son pequenas (`n=9-14`) y eso sobreajustaria la politica. [M1-P5][CALC-1]

### 4. Como evitar alertas duplicadas

- La memoria del motor es por `zona-evento`. [CALC-1]
- Cooldown: `4h`, porque los eventos `moderate+` duran mediana `4h` y maximo `6h`. [CALC-1]
- Reenvio permitido solo si:
  - sube la severidad [CALC-1]
  - el forecast sube `>= 1.0 mm/hr` [CALC-1]
  - la recomendacion cambia `>= 5 MXN` [CALC-1]
- El evento se cierra solo despues de `2` horas consecutivas por debajo de `0.1 mm/hr` o por debajo del trigger activo de la zona. [CALC-1]

## Regla final de notificacion

- Enviar Telegram solo para `alto` y `critico`. [CALC-1]
- Dejar `medio` como watch, salvo el override sensible `1.0-1.9 mm/hr` en peak. [CALC-1]
- Zonas secundarias: rankear primero por vulnerabilidad (`Santiago`, `Carretera Nacional`, `Santa Catarina`, `MTY_Apodaca_Huinala`), luego por monitores de volumen (`Centro`, `San Pedro`, `MTY_Guadalupe`, `San Nicolas`) y despues por cercania de centroides. [M1-P3][CALC-1]

## Conclusión operativa

El motor no usa umbrales arbitrarios: activa en `2.0 mm/hr`, anticipa a `1.0 mm/hr` solo en las cuatro zonas mas sensibles durante lunch/dinner, trabaja con horizonte principal de `1h`, recomienda llevar earnings a `80 MXN` y agrupa cada tormenta en un solo evento de `4h`. Esa combinacion traduce el diagnostico del Modulo 1 en una politica simple, auditable y lista para convertirse en el script funcional de 2c. [M1-P2][M1-P3][M1-P5][CALC-1]

## Referencias

- `[M1-P1]`: [03_kpis_and_findings.ipynb](DataAnalysis/notebooks/03_kpis_and_findings.ipynb), seccion P1; soporte tambien en [resumen_hallazgos_modulo1_1_pagina.md](DataAnalysis/outputs/reports/resumen_hallazgos_modulo1_1_pagina.md).
- `[M1-P2]`: [03_kpis_and_findings.ipynb](DataAnalysis/notebooks/03_kpis_and_findings.ipynb), seccion P2; tablas `DataAnalysis/outputs/tables/p2_rain_bucket_ratio.csv` y `DataAnalysis/outputs/tables/p2_hour_control_ratio_lift.csv`.
- `[M1-P3]`: [03_kpis_and_findings.ipynb](DataAnalysis/notebooks/03_kpis_and_findings.ipynb), seccion P3; tabla `DataAnalysis/outputs/tables/p3_zone_precipitation_sensitivity.csv`.
- `[M1-P5]`: [03_kpis_and_findings.ipynb](DataAnalysis/notebooks/03_kpis_and_findings.ipynb), seccion P5; tabla `DataAnalysis/outputs/tables/p5_earnings_rain_ratio_interaction.csv`.
- `[CALC-1]`: [01_alert_rules_motor_calibration.ipynb](EarlyAlertsAPI/notebooks/01_alert_rules_motor_calibration.ipynb), construido sobre `DataAnalysis/outputs/cleaned/raw_data_clean.parquet` y `DataAnalysis/outputs/cleaned/zone_info_clean.parquet`.
