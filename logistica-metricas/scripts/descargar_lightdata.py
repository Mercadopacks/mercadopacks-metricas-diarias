#!/usr/bin/env python3
"""
descargar_lightdata.py
-----------------------
Inicia sesión en LightData, filtra el listado de envíos por la fecha de
"ayer" (Desde = Hasta = ayer) SIN filtro de Estado — se necesitan todos los
estados (entregado, cancelado, reprogramado, etc.), no solo uno — y descarga
el .xls resultante a datos_crudos/.

Uso:
    LIGHTDATA_USER=... LIGHTDATA_PASS=... python3 descargar_lightdata.py

    El día que se descarga se elige con dos variables de entorno opcionales
    (se evalúan en este orden de prioridad):

    1. FECHA_DESCARGA=YYYY-MM-DD → descarga esa fecha puntual exacta.
       Pensado para backfill manual (ej. si un día quedó con datos viejos
       por un cambio de regla de negocio):

       LIGHTDATA_USER=... LIGHTDATA_PASS=... FECHA_DESCARGA=2026-09-01 python3 descargar_lightdata.py

    2. MODO_FECHA=hoy|ayer → si no hay FECHA_DESCARGA, elige entre el día de
       hoy o el de ayer (ambos en base a la fecha UTC actual — ver nota de
       zona horaria más abajo). Si no se pasa ninguna de las dos variables,
       el default es "ayer" (mismo comportamiento que la versión anterior
       de este script, para no romper nada que ya dependa de él).

    El workflow de GitHub Actions usa MODO_FECHA=hoy en las 4 corridas
    intradía (11/13/15/18hs ART) para traer la "foto" del día en curso, y
    MODO_FECHA=ayer (o nada) en la corrida de las 00hs ART, que cierra el
    día que acaba de terminar.

Pensado para correr sin supervisión (GitHub Actions), por eso:
- Corre el navegador en modo headless.
- Si algo falla, guarda una captura de pantalla para poder diagnosticar sin
  tener que reproducirlo a mano.
- Usa la fecha UTC a propósito para decidir "hoy"/"ayer": todas las corridas
  programadas (11 a 18hs y 00hs Argentina) caen en un horario UTC donde la
  fecha del calendario UTC ya coincide con la fecha del calendario en
  Argentina en el momento exacto de la corrida (Argentina es UTC-3 todo el
  año, sin horario de verano, así que esto es estable). La única corrida
  que necesita "ayer" en vez de "hoy" es la de las 00hs ART (03:00 UTC),
  porque en ese instante la fecha UTC ya avanzó al nuevo día que recién
  empieza en Argentina, y lo que se quiere cerrar es el día anterior.

Los selectores de este script salieron de grabar la navegación real con
`playwright codegen https://mercadopacks.lightdata.app/`. Si LightData
cambia el diseño de la página y el script empieza a fallar, la forma más
rápida de arreglarlo es volver a grabar con esa misma herramienta y
actualizar los selectores de abajo (ver README de la carpeta scripts/).
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

LIGHTDATA_URL = "https://mercadopacks.lightdata.app/"
CARPETA_SALIDA = Path(__file__).resolve().parent.parent / "datos_crudos"
TIMEOUT_MS = 20_000


def seleccionar_dia(page, dia: int):
    """
    Clickea el botón del día indicado en el calendario que está abierto.

    Nota / limitación conocida: si "ayer" cae en el mes anterior (es decir,
    hoy es el día 1 del mes), el calendario podría no mostrar ese día sin
    antes navegar al mes anterior. Esto no se probó todavía porque no
    ocurrió durante la grabación del flujo — si el script falla el primer
    día de cada mes, revisar este paso primero (agregar un click al botón
    de "mes anterior" del picker antes de buscar el día).
    """
    page.get_by_role("button", name=str(dia), exact=True).click()


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


def descargar(usuario: str, clave: str, fecha_objetivo=None, modo_fecha=None) -> Path:
    """
    Ver calcular_fecha_objetivo() para la lógica de qué día se descarga.
    """
    fecha = calcular_fecha_objetivo(fecha_objetivo, modo_fecha)
    dia = fecha.day

    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(TIMEOUT_MS)

        try:
            page.goto(LIGHTDATA_URL)

            page.get_by_role("textbox", name="Username").fill(usuario)
            page.get_by_role("textbox", name="Password").fill(clave)
            page.get_by_text("Ingresar").click()

            # LightData a veces muestra un diálogo de confirmación (p.ej.
            # "ya hay una sesión abierta, ¿continuar?") antes de dejar
            # entrar — se vio durante la primera grabación pero no en la
            # segunda, así que parece depender de si había una sesión
            # previa activa. Si aparece se confirma; si no aparece en unos
            # segundos, se sigue sin problema.
            try:
                page.get_by_role("button", name="OK").click(timeout=5000)
            except PlaywrightTimeoutError:
                pass

            page.get_by_role("link", name="local_shipping Envios").click()
            page.get_by_role("link", name="menu Envios").click()

            page.get_by_role("textbox", name="Fecha desde/hasta").click()
            seleccionar_dia(page, dia)
            page.get_by_role("button", name="Ok").click()

            page.get_by_role("textbox", name="Hasta", exact=True).click()
            seleccionar_dia(page, dia)
            page.get_by_role("button", name="Ok").click()

            # Cierra un chip que a veces queda abierto en el área de fechas
            # tras aplicar el rango — si no está presente, no pasa nada
            # (best-effort, timeout corto).
            try:
                page.get_by_text("×").first.click(timeout=3000)
            except PlaywrightTimeoutError:
                pass

            # Filtro "Estados del envio": se fuerza a "Todos" EXPLÍCITAMENTE,
            # sin asumir que ya viene así por defecto. Se agregó después de
            # un incidente real: este filtro le quedó aplicado a "Pendientes"
            # (se guarda por cuenta en el servidor de LightData, no en el
            # navegador), y el dashboard mostró ~220 envíos de menos porque
            # el .xls descargado ya venía recortado a un solo estado.
            #
            # Es un multi-select de Select2 (admite varios chips a la vez,
            # confirmado viendo la captura real del error: mostraba el chip
            # "× Pendientes" cargado) — por eso la interacción es distinta a
            # un dropdown simple: primero hay que sacar cualquier chip que
            # ya esté puesto, después abrir el desplegable y elegir "Todos".
            #
            # Se ubica el widget con el selector CSS de hermano-adyacente
            # `#envios_f_estado + span.select2` (el <select> real, oculto,
            # con id estable "envios_f_estado" — confirmado en dos
            # grabaciones distintas de esta misma interacción — seguido del
            # <span> que Select2 arma para mostrarlo). No se usa el id de
            # cada opción individual del desplegable porque Select2 lo
            # genera al azar en cada carga de página.
            estado_widget = page.locator("#envios_f_estado + span.select2")
            while estado_widget.locator(".select2-selection__choice__remove").count() > 0:
                estado_widget.locator(".select2-selection__choice__remove").first.click()
            estado_widget.click()
            # OJO: get_by_role("option", ...) matchea también el <option>
            # nativo y oculto del <select> original que Select2 reemplaza
            # visualmente (ambos tienen rol "option" en el árbol de
            # accesibilidad) — eso fue justo lo que falló la vez pasada:
            # resolvía al elemento oculto y nunca se volvía visible. Por eso
            # acá se apunta explícitamente a la clase que Select2 usa para
            # las opciones que SÍ renderiza y muestra en su desplegable.
            page.locator(".select2-results__option").get_by_text("Todos", exact=True).click()

            # Botón "Buscar/Filtrar": no tiene texto visible en la página,
            # por eso el selector es estructural (más frágil ante cambios
            # de diseño que uno por texto o rol).
            page.locator(".row > div:nth-child(3) > .row > div > .btn").first.click()

            with page.expect_download() as download_info:
                with page.expect_popup() as popup_info:
                    # Botón de exportar — mismo caso, sin texto visible.
                    page.locator("div:nth-child(3) > .row > div:nth-child(2) > .btn").click()
                popup = popup_info.value
            download = download_info.value
            popup.close()

        except Exception as e:
            captura = Path(__file__).resolve().parent / "error_descarga.png"
            try:
                page.screenshot(path=str(captura))
            except Exception:
                pass  # si la página ya no responde, seguimos sin la captura
            context.close()
            browser.close()
            tipo = "Timeout" if isinstance(e, PlaywrightTimeoutError) else type(e).__name__
            raise RuntimeError(
                f"{tipo} en el flujo de LightData. Se guardó una captura de "
                f"pantalla en {captura} para diagnosticar. Error original: {e}"
            )

        nombre = "listado_envios_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + ".xls"
        destino = CARPETA_SALIDA / nombre
        download.save_as(str(destino))

        context.close()
        browser.close()

    return destino


def main():
    usuario = os.environ.get("LIGHTDATA_USER")
    clave = os.environ.get("LIGHTDATA_PASS")
    if not usuario or not clave:
        sys.exit("Faltan las variables de entorno LIGHTDATA_USER / LIGHTDATA_PASS.")

    fecha_objetivo = None
    fecha_str = os.environ.get("FECHA_DESCARGA", "").strip()
    if fecha_str:
        try:
            fecha_objetivo = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            sys.exit(f"FECHA_DESCARGA debe tener formato YYYY-MM-DD, se recibió: {fecha_str!r}")

    modo_fecha = os.environ.get("MODO_FECHA", "").strip().lower()

    destino = descargar(usuario, clave, fecha_objetivo, modo_fecha)
    print(f"Archivo descargado: {destino}")


if __name__ == "__main__":
    main()
