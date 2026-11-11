#!/usr/bin/env python3
"""
descargar_lightdata_api.py
----------------------------
Alternativa a `descargar_lightdata.py` (que loguea con Playwright y
descarga un .xls desde la UI) usando en cambio la API externa de
LightData (`POST /externa/consultar-fecha`), documentada en
https://lightdata.app/documentacion_api_externa.html — sin navegador, sin
LibreOffice, sin selectores que se rompen si LightData cambia el diseño.

ESTADO (2026-11-11): escrito contra la documentación de la API, pero
TODAVÍA NO VALIDADO con datos reales — el endpoint `consultar-fecha`
devuelve "Empresa no habilitada" para la empresa 253 hasta que LightData lo
habilite (ver reglas_de_negocio.md sección 14). NO está conectado al
workflow de GitHub Actions todavía. Antes de reemplazar
`descargar_lightdata.py` en el workflow:
  1. Confirmar que LightData habilitó el endpoint para la empresa 253.
  2. Correr este script a mano para un día ya conocido (ej. ayer) y
     comparar fila por fila contra el .xls real del mismo día, en
     especial: nombres exactos de `Estado` (¿"Entregado 2DA visita" viene
     igual? ¿"reprogramado por meli" en minúsculas como en LightData UI?),
     y qué campo de fecha de la API corresponde realmente a
     "Fecha MercadoPacks" (día de ingreso al sistema) — ver el TODO en
     `_mapear_fila` más abajo, donde por ahora se deja ese campo vacío a
     propósito (fuerza el fallback a "Fecha estado" en fecha_operativa() de
     publicar_firestore.py, que si sabemos que es correcto) en vez de
     adivinar mal un campo tan sensible para las reglas de negocio.
  3. Recién ahí cambiar el workflow para usar este script en vez del de
     Playwright.

Uso (mismas variables de entorno que descargar_lightdata.py para elegir
el día — FECHA_DESCARGA / MODO_FECHA):

    LIGHTDATA_API_TOKEN=ldae_253_xxx LIGHTDATA_API_ID_EMPRESA=253 \
        python3 descargar_lightdata_api.py

Guarda un .csv (no .xls) en datos_crudos/ con los mismos nombres de
columna que espera `generar_reporte.procesar()`, e imprime
"Archivo descargado: <ruta>" — mismo contrato que descargar_lightdata.py,
para que publicar_firestore.py no tenga que cambiar.
"""

import csv
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from fecha_descarga import calcular_fecha_objetivo

API_BASE = "https://apiexterna.lightdata.com.ar/externa"
CARPETA_SALIDA = Path(__file__).resolve().parent.parent / "datos_crudos"
CANTIDAD_POR_PAGINA = 1000
TIMEOUT_S = 30

# Offset fijo de Argentina respecto a UTC (UTC-3 todo el año, sin horario
# de verano — mismo supuesto ya usado en descargar_lightdata.py).
OFFSET_ART = timedelta(hours=-3)

# Origen: 0 Directo, 1 Mercado Libre, 2 TN, 3 Shopify, 4 Woo, 5 Presta,
# 6 VTEX, 7 Falabella, 8 Jumpseller (tabla de la documentación de la API).
# El texto de la derecha debe coincidir con los valores de `Origen` que ya
# usa el resto del pipeline (diccionario_de_datos.md) para los códigos que
# existían antes de la API; los códigos 3-8 son categorías nuevas que el
# export de LightData nunca mostró hasta ahora (no hay evidencia todavía
# de que Mercadopacks opere alguno de esos canales) — se mapean con su
# nombre de plataforma por si aparecen, pero no están confirmados contra
# datos reales.
ORIGEN_POR_CODIGO = {
    0: "Directo",
    1: "ML",  # salvo turbo=1, ver _origen_texto()
    2: "TNube",
    3: "Shopify",
    4: "Woo",
    5: "Presta",
    6: "VTEX",
    7: "Falabella",
    8: "Jumpseller",
}


def _origen_texto(origen_codigo, turbo) -> str:
    base = ORIGEN_POR_CODIGO.get(origen_codigo, "")
    if origen_codigo == 1 and turbo:
        return "ML TURBO"
    return base


def _iso_a_fecha_hora_art(valor_iso) -> str:
    """
    Convierte una fecha ISO8601 en UTC (con sufijo 'Z', como devuelve la
    API) al formato 'dd/mm/aaaa HH:MM' en hora de Argentina (UTC-3), que es
    el formato que espera `procesar()` de generar_reporte.py para
    'Fecha estado' (COLUMNA_TIMESTAMP_ENTREGA). Devuelve '' si el valor
    viene vacío/None (mismo criterio que una celda vacía en el .xls real).
    """
    if not valor_iso:
        return ""
    try:
        dt_utc = datetime.fromisoformat(str(valor_iso).replace("Z", "+00:00"))
    except ValueError:
        return ""
    dt_art = dt_utc.astimezone(timezone.utc) + OFFSET_ART
    return dt_art.strftime("%d/%m/%Y %H:%M")


def _mapear_fila(envio: dict) -> dict:
    """
    Traduce un registro de la API al mismo esquema de columnas que
    `cargar_export()` produce a partir del .xls real (ver
    diccionario_de_datos.md), usando solo los nombres de columna que el
    resto del pipeline (`procesar()`, `calcular_snapshots()`,
    `calcular_detalle_por_chofer()`) efectivamente lee. Las columnas del
    .xls que la API no devuelve (ej. 'Método de envío', peso/bultos,
    teléfono/email del destinatario) quedan vacías a propósito — ninguna
    regla de negocio actual las usa.
    """
    origen_codigo = envio.get("origen")
    turbo = envio.get("turbo")

    return {
        "ID (Interno)": envio.get("idEnvio", ""),
        "Número Tracking": envio.get("shipment_id") or envio.get("idEnvio", ""),
        "ID venta ML": envio.get("id_venta", ""),
        "Fecha Venta": _iso_a_fecha_hora_art(envio.get("fecha_venta")),
        "Fecha Colecta": _iso_a_fecha_hora_art(envio.get("fecha_colecta")),
        # TODO (ver cabecera del archivo): no está confirmado qué campo de
        # la API corresponde a "día de ingreso al sistema". Se deja vacío
        # a propósito para forzar el fallback a "Fecha estado" en
        # fecha_operativa() (publicar_firestore.py), que si es un mapeo
        # confirmado (fecha_ultimo_estado). No adivinar esto sin comparar
        # contra un día real primero.
        "Fecha MercadoPacks": "",
        "Zona": envio.get("zona", ""),
        "Estado": envio.get("estado", ""),
        "Fecha estado": _iso_a_fecha_hora_art(envio.get("fecha_ultimo_estado")),
        "Cadete": envio.get("chofer", ""),
        "Fecha de asignación": _iso_a_fecha_hora_art(envio.get("fecha_asignacion")),
        "Origen": _origen_texto(origen_codigo, turbo),
        "Nombre Fantasia": envio.get("cliente", ""),
        "Localidad": envio.get("localidad", ""),
        "CP": envio.get("cp", ""),
        "Precio": envio.get("costo_envio", ""),
        "Total a cobrar": envio.get("monto_a_cobrar", "") if envio.get("tiene_cobranza") else "",
    }


def consultar_fecha(token: str, id_empresa: int, fecha) -> list:
    """
    Pagina sobre POST /externa/consultar-fecha para un único día
    (00:00:00 a 23:59:59, hora de Argentina — la API interpreta las fechas
    de entrada en ese huso, según la documentación) y devuelve la lista
    completa de envíos de ese día.
    """
    desde = f"{fecha.isoformat()} 00:00:00"
    hasta = f"{fecha.isoformat()} 23:59:59"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    envios = []
    pagina = 1
    total_paginas = 1
    while pagina <= total_paginas:
        body = {
            "idEmpresa": id_empresa,
            "fecha_desde": desde,
            "fecha_hasta": hasta,
            "paginacion": 1,
            "pagina": pagina,
            "cantidad": CANTIDAD_POR_PAGINA,
        }
        resp = requests.post(
            f"{API_BASE}/consultar-fecha", json=body, headers=headers, timeout=TIMEOUT_S
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"consultar-fecha devolvió HTTP {resp.status_code} en la página "
                f"{pagina}: {resp.text[:500]}"
            )
        data = resp.json()
        if not data.get("success", False):
            raise RuntimeError(f"consultar-fecha respondió success=false: {data}")

        lote = data.get("data", [])
        envios.extend(lote)

        meta = data.get("meta", {})
        total_paginas = meta.get("total_paginas", 1) or 1
        pagina += 1
        if pagina <= total_paginas:
            time.sleep(1.5)  # margen de sobra contra el límite de 50 req/min

    return envios


def descargar(token: str, id_empresa: int, fecha_objetivo=None, modo_fecha=None) -> Path:
    fecha = calcular_fecha_objetivo(fecha_objetivo, modo_fecha)

    envios = consultar_fecha(token, id_empresa, fecha)

    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)
    nombre = "listado_envios_api_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + ".csv"
    destino = CARPETA_SALIDA / nombre

    columnas = [
        "ID (Interno)", "Número Tracking", "ID venta ML", "Fecha Venta",
        "Fecha Colecta", "Fecha MercadoPacks", "Zona", "Estado",
        "Fecha estado", "Cadete", "Fecha de asignación", "Origen",
        "Nombre Fantasia", "Localidad", "CP", "Precio", "Total a cobrar",
    ]
    with open(destino, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columnas)
        writer.writeheader()
        for envio in envios:
            writer.writerow(_mapear_fila(envio))

    return destino


def main():
    token = os.environ.get("LIGHTDATA_API_TOKEN")
    id_empresa_str = os.environ.get("LIGHTDATA_API_ID_EMPRESA")
    if not token or not id_empresa_str:
        sys.exit("Faltan las variables de entorno LIGHTDATA_API_TOKEN / LIGHTDATA_API_ID_EMPRESA.")
    id_empresa = int(id_empresa_str)

    fecha_objetivo = None
    fecha_str = os.environ.get("FECHA_DESCARGA", "").strip()
    if fecha_str:
        try:
            fecha_objetivo = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            sys.exit(f"FECHA_DESCARGA debe tener formato YYYY-MM-DD, se recibió: {fecha_str!r}")

    modo_fecha = os.environ.get("MODO_FECHA", "").strip().lower()

    destino = descargar(token, id_empresa, fecha_objetivo, modo_fecha)
    print(f"Archivo descargado: {destino}")


if __name__ == "__main__":
    main()
