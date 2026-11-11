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


def calcular_fecha_objetivo(fecha_objetivo, modo_fecha):
    """
    Resuelve qué fecha descargar, en este orden de prioridad:
    1. fecha_objetivo explícita (backfill manual de un día puntual).
    2. modo_fecha == "hoy" → fecha UTC actual (coincide con la fecha
       argentina en todos los horarios intradía programados).
    3. cualquier otro caso (modo_fecha == "ayer", vacío, o no reconocido)
       → fecha UTC actual menos un día — comportamiento histórico/default,
       usado por la corrida de cierre de las 00hs ART.
    """
    if fecha_objetivo:
        return fecha_objetivo
    hoy_utc = datetime.now(timezone.utc).date()
    if modo_fecha == "hoy":
        return hoy_utc
    return hoy_utc - timedelta(days=1)
