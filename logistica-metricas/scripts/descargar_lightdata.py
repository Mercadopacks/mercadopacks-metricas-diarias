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


def _modal_de_calendario_abierto(page):
    """
    Devuelve el contenedor del modal de Materialize que está REALMENTE
    abierto en este momento (clase `.modal.open` — convención propia y
    documentada de Materialize, no un supuesto nuevo: es la misma clase que
    el propio framework agrega/saca al abrir/cerrar un modal).

    Hace falta escalear todo a este contenedor porque LightData puede tener
    más de una instancia del date picker en el DOM al mismo tiempo (se
    confirmó en un backfill real: `select.orig-select-month` resolvió a 2
    elementos en vez de 1, con el calendario recién abierto por primera vez
    — todavía no está claro por qué hay una segunda instancia, pero da
    igual: filtrando por cuál modal está efectivamente abierto, el resto de
    los selectores dejan de ser ambiguos sin depender de entender esa causa).
    """
    modal = page.locator(".modal.open")
    n = modal.count()
    if n == 0:
        raise RuntimeError(
            "No se encontró ningún '.modal.open' — el calendario de LightData "
            "no se abrió como se esperaba, o cambió de estructura (ya no usa "
            "el modal de Materialize). Revisar con playwright codegen antes "
            "de reintentar, no adivinar selectores nuevos."
        )
    # Si por lo que sea hay más de un modal marcado "open" a la vez, nos
    # quedamos con el más reciente (el último en el DOM) en vez de fallar —
    # es la opción más razonable sin más información, y de todas formas cada
    # paso de abajo tiene su propio chequeo de "no encontrado".
    return modal.last if n > 1 else modal


def navegar_a_mes(page, fecha):
    """
    Navega el calendario (el date picker nativo de Materialize CSS — NO es
    Angular Material, un intento anterior de este fix asumió mal el
    framework a partir de una sola captura y falló en producción con un
    timeout) hasta el mes/año de `fecha`, clickeando "mes anterior"/"mes
    siguiente" las veces que haga falta, todo escaleado dentro del modal
    que está realmente abierto (ver `_modal_de_calendario_abierto`).

    Selectores confirmados inspeccionando el HTML real del picker (no
    adivinados): el botón "mes anterior" es `button.month-prev` (por
    simetría con el de Materialize, "mes siguiente" es `button.month-next`),
    y el mes/año actual se lee de dos `<select>` nativos que Materialize
    mantiene ocultos pero sincronizados con la UI visible
    (`select.orig-select-month`, con valores 0=Enero...11=Diciembre, y
    `select.orig-select-year`) — mucho más confiable que parsear un texto
    visible que podría cambiar de idioma. `input_value()` funciona sobre
    estos selects aunque Materialize los mantenga ocultos a propósito (es
    una lectura del DOM, no una interacción que requiera visibilidad).

    Bug real que esto corrige (2026-10-01): antes, seleccionar_dia() solo
    clickeaba el botón del número de día en el mes que el calendario tuviera
    abierto por default — el mes de "hoy" en LightData, no el mes de la
    fecha pedida. La corrida de cierre de las 00hs ART (que además repasa
    los 2 días anteriores, ver reglas_de_negocio.md regla #5) cae justo
    después de medianoche: el 1° de octubre pidió los días 30/29/28 de
    SEPTIEMBRE, pero el calendario abría en OCTUBRE — y como esos mismos
    números de día también existen en octubre, el script clickeaba la
    fecha equivocada sin ningún error visible. LightData devolvía 0 filas
    para ese rango y el snapshot de esos 3 días quedó sin actualizar, en
    silencio (incidente real: envios_daily/2026-09-30, 2026-09-29 y
    2026-09-28 no se actualizaron con la corrida de cierre del
    2026-10-01T03:00 UTC, aunque el workflow de GitHub Actions marcó esa
    corrida como exitosa).
    """
    modal = _modal_de_calendario_abierto(page)
    boton_anterior = modal.locator("button.month-prev")
    boton_siguiente = modal.locator("button.month-next")
    select_mes = modal.locator("select.orig-select-month")
    select_anio = modal.locator("select.orig-select-year")

    # Falla rápido y con un mensaje claro si cambió la estructura del picker,
    # en vez de un timeout críptico de 20s esperando un selector que no
    # existe (lo que pasó con el intento anterior, que asumió mal el
    # framework del date picker).
    if (
        boton_anterior.count() == 0 or boton_siguiente.count() == 0
        or select_mes.count() == 0 or select_anio.count() == 0
    ):
        raise RuntimeError(
            "No se encontraron los controles de navegación dentro del modal "
            "de calendario abierto (button.month-prev / button.month-next / "
            "select.orig-select-month / select.orig-select-year) — puede que "
            "haya cambiado la estructura del date picker. Revisar con "
            "playwright codegen antes de reintentar, no adivinar selectores nuevos."
        )

    objetivo_idx = fecha.year * 12 + (fecha.month - 1)

    for _ in range(36):  # tope de seguridad: 3 años de margen, nunca debería hacer falta tanto
        mes_actual = int(select_mes.input_value())  # 0=Enero ... 11=Diciembre
        anio_actual = int(select_anio.input_value())
        actual_idx = anio_actual * 12 + mes_actual
        diferencia = objetivo_idx - actual_idx
        if diferencia == 0:
            return
        (boton_siguiente if diferencia > 0 else boton_anterior).click()

    raise RuntimeError(
        f"No se pudo navegar el calendario hasta el mes {fecha.month}/{fecha.year} "
        "después de 36 intentos — puede que haya cambiado la estructura del "
        "date picker de LightData."
    )


def seleccionar_dia(page, fecha):
    """
    Navega al mes de `fecha` (ver navegar_a_mes) y clickea el botón del día
    indicado, dentro del modal que está realmente abierto — mismo motivo que
    en navegar_a_mes: puede haber más de una instancia del calendario en el
    DOM, y el número de día (ej. "28") existe en cualquiera de ellas.
    """
    navegar_a_mes(page, fecha)
    modal = _modal_de_calendario_abierto(page)
    modal.get_by_role("button", name=str(fecha.day), exact=True).click()


def seleccionar_estado_todos(page):
    """
    Fuerza el filtro "Estados del envio" a "Todos" EXPLÍCITAMENTE, sin
    asumir que ya viene así por defecto.

    Se agregó después de un incidente real: este filtro le quedó aplicado a
    "Pendientes" (se guarda por cuenta en el servidor de LightData, no en
    el navegador), y el dashboard mostró ~220 envíos de menos porque el
    .xls descargado ya venía recortado a un solo estado.

    Es un multi-select de Select2 (admite varios chips a la vez, confirmado
    viendo la captura real del error: mostraba el chip "× Pendientes"
    cargado) — por eso la interacción es distinta a un dropdown simple:
    primero hay que sacar cualquier chip que ya esté puesto, después abrir
    el desplegable y elegir "Todos".

    Se ubica el widget con el selector CSS de hermano-adyacente
    `#envios_f_estado + span.select2` (el <select> real, oculto, con id
    estable "envios_f_estado" — confirmado en dos grabaciones distintas de
    esta misma interacción — seguido del <span> que Select2 arma para
    mostrarlo). No se usa el id de cada opción individual del desplegable
    porque Select2 lo genera al azar en cada carga de página.

    Esta función tiene un test de regresión que la ejecuta contra una
    página local con la librería real de Select2 (sin depender de
    LightData): ver tests/test_estado_lightdata.py. Si se vuelve a tocar
    esta lógica, correr ese test antes de subir cambios.
    """
    estado_widget = page.locator("#envios_f_estado + span.select2")
    while estado_widget.locator(".select2-selection__choice__remove").count() > 0:
        estado_widget.locator(".select2-selection__choice__remove").first.click()
    # OJO: sacar un chip deja el desplegable YA ABIERTO solo (Select2 reabre
    # la búsqueda al perder un chip). Un click de más ahí lo CIERRA de
    # nuevo, porque Select2 alterna abierto/cerrado en cada click — eso fue
    # justo lo que pasó la primera vez que se armó este fix (reproducido y
    # confirmado en el test local). Por eso solo se hace click para abrir
    # si TODAVÍA no está abierto.
    if page.locator(".select2-results__option").count() == 0:
        estado_widget.click()
    # OJO 2: get_by_role("option", ...) matchea también el <option> nativo
    # y oculto del <select> original que Select2 reemplaza visualmente
    # (ambos tienen rol "option" en el árbol de accesibilidad) — resolvía
    # al elemento oculto y nunca se volvía visible. Por eso acá se apunta
    # explícitamente a la clase que Select2 usa para las opciones que SÍ
    # renderiza y muestra.
    page.locator(".select2-results__option").get_by_text("Todos", exact=True).click()


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
            seleccionar_dia(page, fecha)
            page.get_by_role("button", name="Ok").click()

            page.get_by_role("textbox", name="Hasta", exact=True).click()
            seleccionar_dia(page, fecha)
            page.get_by_role("button", name="Ok").click()

            # Cierra un chip que a veces queda abierto en el área de fechas
            # tras aplicar el rango — si no está presente, no pasa nada
            # (best-effort, timeout corto).
            try:
                page.get_by_text("×").first.click(timeout=3000)
            except PlaywrightTimeoutError:
                pass

            seleccionar_estado_todos(page)

            # Botones "Buscar/Filtrar" y "Exportar": NO son <button>
            # semánticos con texto accesible utilizable (confirmado con dos
            # intentos fallidos: get_by_role con "FILTRAR" no matcheaba
            # nada, get_by_text tampoco — el texto visible en pantalla no
            # es un nodo de texto real que Playwright pueda bindear). El
            # selector correcto es estructural, pero tiene que estar
            # ANCLADO al contenedor del módulo de Envíos (#envios_listado)
            # — confirmado grabando de nuevo la interacción real con
            # `playwright codegen` (2026-09-19). Sin ese anclaje, el
            # selector puede "escaparse" y agarrar un botón con la misma
            # forma en OTRO módulo de la página (pasó de verdad: agarró
            # "Descarga masiva choferes" de Liquidación de Cobranzas).
            page.locator(
                "#envios_listado > .card > .card-content > div > div:nth-child(3) > .row > div > .btn"
            ).first.click()

            with page.expect_download() as download_info:
                with page.expect_popup() as popup_info:
                    page.locator(
                        "#envios_listado > .card > .card-content > div > div:nth-child(3) > .row > div:nth-child(2) > .btn"
                    ).click()
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
