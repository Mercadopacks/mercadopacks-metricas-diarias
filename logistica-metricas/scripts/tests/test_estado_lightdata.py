#!/usr/bin/env python3
"""
test_estado_lightdata.py
-------------------------
Prueba de regresión para `seleccionar_estado_todos()` (en
`descargar_lightdata.py`), sin depender de LightData ni de credenciales.

Corre la MISMA función que usa la descarga real contra una página local que
usa la librería real de Select2 (vendorizada en `vendor/`, misma versión que
LightData) armada para reproducir el campo real "Estados del envio": un
multi-select donde puede haber 0, 1 o varios chips ya seleccionados.

Se armó después de un incidente real (2026-09-09): el filtro de Estado le
quedó aplicado a "Pendientes" en vez de "Todos", y el fix se estuvo
iterando "a ciegas" contra producción varias veces sin encontrar la causa.
Reproducir el bug en local (con la librería real de Select2) permitió
encontrar la causa real en minutos: sacar un chip deja el desplegable ya
abierto, y un click de más lo vuelve a cerrar.

Uso:
    cd logistica-metricas/scripts/tests
    python3 test_estado_lightdata.py

Sale con código 0 si los 4 casos pasan, 1 si alguno falla.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from descargar_lightdata import seleccionar_estado_todos  # noqa: E402

from playwright.sync_api import sync_playwright

FIXTURE_PATH = Path(__file__).resolve().parent / "fixture_estado_select2.html"

CASOS = [
    ("pendientes_seleccionado", ["1"]),   # el incidente real: quedó en "Pendientes"
    ("todos_ya_seleccionado", ["-1"]),    # ya estaba bien, no debería romper nada
    ("sin_seleccion", []),                # caso más simple, sin chips
    ("multiples_chips", ["1", "3", "4"]),  # varios estados marcados a la vez
]


def valor_actual(page):
    return page.eval_on_selector(
        "#envios_f_estado", "el => Array.from(el.selectedOptions).map(o => o.text)"
    )


def correr_caso(nombre: str, valor_inicial: list) -> bool:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file:///{FIXTURE_PATH.as_posix()}")
        page.wait_for_selector("#envios_f_estado + span.select2")

        page.evaluate(
            "(v) => { $('#envios_f_estado').val(v).trigger('change'); }",
            valor_inicial,
        )
        page.wait_for_timeout(200)
        antes = valor_actual(page)

        try:
            seleccionar_estado_todos(page)
            page.wait_for_timeout(200)
            despues = valor_actual(page)
            ok = despues == ["Todos"]
        except Exception as e:
            print(f"  [{nombre}] EXCEPCION: {type(e).__name__}: {str(e)[:200]}")
            despues = None
            ok = False

        print(f"  [{nombre}] antes={antes} -> despues={despues} -> {'OK' if ok else 'FALLO'}")
        browser.close()
        return ok


def main():
    print("Corriendo test_estado_lightdata.py ...")
    resultados = [correr_caso(nombre, valor) for nombre, valor in CASOS]
    todo_ok = all(resultados)
    print("\nRESULTADO FINAL:", "TODOS OK" if todo_ok else "HAY FALLOS")
    sys.exit(0 if todo_ok else 1)


if __name__ == "__main__":
    main()
