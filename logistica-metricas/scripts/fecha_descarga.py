#!/usr/bin/env python3
"""
fecha_descarga.py
-------------------
Lógica de "qué día descargar", compartida entre descargar_lightdata.py
(Playwright) y descargar_lightdata_api.py (API externa de LightData).
Separado en su propio módulo para que el script de API no tenga que
importar playwright solo para esta función — justamente uno de los puntos
de la migración a la API es dejar de depender de un navegador.
"""

from datetime import datetime, timedelta, timezone

# Argentina es UTC-3 todo el año (sin horario de verano) — se usa esta
# resta fija en vez de zoneinfo/TZ para no depender de que el entorno
# tenga la base de datos de husos horarios instalada (ver nota de
# "bug real" más abajo, el mismo criterio que ya usaba
# descargar_lightdata.py antes de este archivo existir).
OFFSET_ART = timedelta(hours=-3)


def calcular_fecha_objetivo(fecha_objetivo, modo_fecha):
    """
    Resuelve qué fecha descargar, en este orden de prioridad:
    1. fecha_objetivo explícita (backfill manual de un día puntual).
    2. modo_fecha == "hoy" → fecha de Argentina actual.
    3. cualquier otro caso (modo_fecha == "ayer", vacío, o no reconocido)
       → fecha de Argentina actual menos un día — comportamiento
       histórico/default, usado por la corrida de cierre de las 00hs ART.

    Bug real corregido el 2026-11-11: antes se usaba la fecha UTC
    (`datetime.now(timezone.utc).date()`) directo, asumiendo que
    coincidía con la fecha de Argentina — cierto solo mientras las
    corridas de "hoy" ocurrían entre las 14:00 y las 21:00 UTC (11:00 a
    18:00 ART), un rango que nunca cruza la medianoche UTC. Al extender
    las corridas intradía hasta las 23:40 ART (seguimiento de
    repartidores en tiempo real), una corrida a las 22:00 ART cae en
    01:00 UTC del día calendario SIGUIENTE — con la fecha UTC cruda,
    "hoy" terminaba siendo el día de mañana en vez de hoy. Ahora se
    convierte el instante UTC a su equivalente en ART antes de tomar
    `.date()`, así "hoy" siempre es el día de Argentina sin importar a
    qué hora UTC se invoque este script.
    """
    if fecha_objetivo:
        return fecha_objetivo
    hoy_art = (datetime.now(timezone.utc) + OFFSET_ART).date()
    if modo_fecha == "hoy":
        return hoy_art
    return hoy_art - timedelta(days=1)
