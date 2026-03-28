# Resumen de hallazgos - Modulo 1

**Scope del analisis**
- Ciudad: Monterrey
- Periodo: 30 dias
- Grano: zona x hora (`10,080` observaciones)
- KPI central: `RATIO = ORDERS / CONNECTED_RT`

**Resumen ejecutivo**

El desbalance operativo no es uniforme durante el dia: se concentra en hotspots repetibles de lunch (`12:00-14:00`) y dinner (`19:00-21:00`). A nivel ciudad, `24.8%` de las zona-hora cae en rango saludable (`0.9-1.2`), `22.4%` en sobre-oferta (`RATIO < 0.5`) y `5.1%` en saturacion (`RATIO > 1.8`). La lluvia es el principal estresor contextual y la calibracion actual de earnings/incentives muestra problemas de timing: hay overspend amplio en horas de baja presion y pockets de under-investment justo en las horas criticas.

**1. Saturacion critica por hora y zona (P1)**

Lunch concentra el mayor riesgo: `14:00` (`27.9%` de las observaciones de esa hora en saturacion), `13:00` (`26.0%`) y `12:00` (`24.5%`), seguidas por `21:00` (`16.2%`), `19:00` (`12.4%`) y `20:00` (`12.1%`). A nivel de zona completa destacan `San Nicolas` y `Santiago` (`6.25%` de sus horas saturadas), pero el mejor indicador operativo es `zona x hora`: `MTY_Guadalupe-14:00` y `Mitras Centro-13:00` se saturan en `40%` de los dias; `San Nicolas-14:00` y `San Nicolas-20:00` en `36.7%`.

**2. Lluvia como variable externa (P2)**

`PRECIPITATION_MM` tiene una correlacion Spearman positiva pero debil con `RATIO` (`r=0.2307`), por lo que el efecto no debe leerse como una regla global fuerte. La senal real aparece al segmentar: el `RATIO` promedio sube de `0.775` en `no_rain` a `1.700` en `moderate` y `1.769` en `heavy`, mientras la saturacion pasa de `3.7%` a `31.2%-33.9%`. La demanda crece mas rapido que la oferta: en `moderate`, pedidos `+12.25` vs no-rain y riders `+4.16`; en `heavy`, pedidos `+14.64` y riders `+6.24`.

**3. Vulnerabilidad por zona (P3)**

Todas las zonas empeoran con lluvia, pero hay dos lentes distintos. Por deterioro relativo de `RATIO`, las mas sensibles son `Santiago` (`+1.821`), `Carretera Nacional` (`+1.484`), `MTY_Apodaca_Huinala` (`+1.061`) y `Santa Catarina` (`+0.991`). Por gap absoluto demanda-oferta (`orders_lift - connected_rt_lift`), destacan `Centro` (`+13.807`), `San Pedro` (`+12.075`), `MTY_Guadalupe` (`+10.089`) y `San Nicolas` (`+9.960`). Esto sugiere proteger primero las zonas con mayor lift relativo y monitorear aparte las zonas de mayor volumen.

**4. Calibracion de earnings e ineficiencia (P4)**

A nivel diario aparecen `8` dias de overspend y `0` dias de under-investment con la regla agregada, pero esa vista es enganosa. Intradia, el overspend es amplio en ventanas de baja presion (`2024-03-22`: `71` zona-hora; `2024-03-14`: `66`; `2024-03-03`: `62`; `2024-03-07`: `61`), mientras el under-investment aparece en bolsillos mas pequenos pero repetidos (`2024-03-14` y `2024-03-19`: `10` zona-hora; `2024-03-23`, `2024-03-26` y `2024-03-30`: `9`). Los pockets de under-investment se concentran casi por completo en `12:00-14:00` y `19:00-21:00`.

**5. Relacion entre earnings y saturacion (P5)**

En agregado, `EARNINGS` vs `RATIO` tiene una relacion muy debil (`r=0.0761`), asi que no existe una regla global util. Al comparar dentro de la misma condicion de lluvia, el patron cambia: `light` no es concluyente (`p=0.069`), pero en `moderate` y `heavy` la relacion es claramente negativa (`r=-0.4172` y `r=-0.6979`). En `heavy`, `Q4_high` muestra `RATIO=1.336` y `9.9%` de saturacion, frente a `Q2-Q3` con `RATIO=2.084-2.352` y `59.2%-62.5%`; en `moderate`, `Q4_high` cae a `1.414` y `13.0%` frente a `1.906-2.042` y `41.2%-55.3%`. Los buckets lluviosos de `Q1_low` son consistentes pero pequenos y deben leerse con cautela.

**Implicacion operativa**

La prioridad para Modulo 2 es pasar de reglas diarias a reglas `zona x hora x lluvia`: reforzar lunch/dinner hotspots, escalar incentivos por intensidad de lluvia y usar safeguards de muestra minima antes de traducir lifts observados en politica operativa.
