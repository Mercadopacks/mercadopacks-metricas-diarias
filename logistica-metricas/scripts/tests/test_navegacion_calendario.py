#!/usr/bin/env python3
"""
test_navegacion_calendario.py
-------------------------------
Prueba de regresión para `navegar_a_mes()` (en `descargar_lightdata.py`),
sin depender de LightData ni de un navegador real.

Incidente real que esto corrige (2026-10-01): `seleccionar_dia()` clickeaba
el número de día en el mes que el calendario de LightData tuviera abierto
por default, sin navegar. La corrida de cierre de las 00hs ART del 1° de
octubre pidió los días 30/29/28 de SEPTIEMBRE, pero el calendario abría en
OCTUBRE — y como esos números de día también existen en octubre, clickeó la
fecha equivocada sin ningún error visible. LightData devolvió 0 filas y el
snapshot de esos 3 días quedó sin actualizar, EN SILENCIO (el workflow de
GitHub Actions marcó esa corrida como exitosa).

El primer intento de arreglo asumió (a partir de una sola captura) que el
date picker era de Angular Material y leía el mes/año de un botón de texto
— falló en producción con un timeout porque ese selector no existe: el
picker real es el de Materialize CSS, y el mes/año se leen de dos `<select>`
nativos (`orig-select-month`/`orig-select-year`) que Materialize mantiene
ocultos pero sincronizados. Esta prueba usa un "calendario falso" en Python
que simula ese contrato exacto (leer `.input_value()` de los selects,
clickear anterior/siguiente) — mismo patrón de "probar la lógica real
contra un doble simple" que ya se usa en este proyecto para el filtro de
Estado.

Uso:
    cd logistica-metricas/scripts/tests
    python3 test_navegacion_calendario.py

Sale con código 0 si todos los casos pasan, 1 si alguno falla.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from descargar_lightdata import navegar_a_mes  # noqa: E402


class CalendarioFalso:
    """Simula el estado interno del date picker: un mes (0-11) / año actual
    que cambia cuando se clickea anterior/siguiente — igual que los
    `<select>` ocultos de Materialize."""

    def __init__(self, anio: int, mes_idx: int, roto: bool = False):
        self.anio = anio
        self.mes_idx = mes_idx  # 0=Enero ... 11=Diciembre
        self.roto = roto  # si True, los botones no cambian nada (para probar el tope de seguridad)
        self.clicks_anterior = 0
        self.clicks_siguiente = 0
        self.existe = True  # para simular un picker con estructura distinta/rota

    def mes_anterior(self):
        self.clicks_anterior += 1
        if self.roto:
            return
        self.mes_idx -= 1
        if self.mes_idx < 0:
            self.mes_idx = 11
            self.anio -= 1

    def mes_siguiente(self):
        self.clicks_siguiente += 1
        if self.roto:
            return
        self.mes_idx += 1
        if self.mes_idx > 11:
            self.mes_idx = 0
            self.anio += 1


class LocatorFalso:
    def __init__(self, calendario: CalendarioFalso, kind: str):
        self.calendario = calendario
        self.kind = kind

    def count(self):
        if not self.calendario.existe:
            return 0
        return 1

    def input_value(self):
        if self.kind == "mes":
            return str(self.calendario.mes_idx)
        if self.kind == "anio":
            return str(self.calendario.anio)
        raise AssertionError("solo los selects tienen input_value()")

    def click(self):
        if self.kind == "prev":
            self.calendario.mes_anterior()
        elif self.kind == "next":
            self.calendario.mes_siguiente()
        else:
            raise AssertionError("solo los botones prev/next se clickean")


class PageFalsa:
    def __init__(self, calendario: CalendarioFalso):
        self.calendario = calendario

    def locator(self, selector: str):
        if "month-prev" in selector:
            return LocatorFalso(self.calendario, "prev")
        if "month-next" in selector:
            return LocatorFalso(self.calendario, "next")
        if "orig-select-month" in selector:
            return LocatorFalso(self.calendario, "mes")
        if "orig-select-year" in selector:
            return LocatorFalso(self.calendario, "anio")
        raise AssertionError(f"selector inesperado: {selector}")


CASOS_OK = [
    # (nombre, (año, mes_idx 0-11) actual del calendario, fecha objetivo, clicks "anterior" esperados, clicks "siguiente" esperados)
    ("ya_esta_en_el_mes_correcto", (2026, 8), date(2026, 9, 30), 0, 0),
    # el incidente real: calendario en octubre (idx 9), se pide un día de septiembre (idx 8)
    ("un_mes_atras_mismo_anio", (2026, 9), date(2026, 9, 30), 1, 0),
    ("tres_meses_atras", (2026, 11), date(2026, 9, 28), 3, 0),
    # cruce de año hacia atrás (ej. corrida de cierre del 1° de enero)
    ("cruce_de_anio_atras", (2027, 0), date(2026, 10, 15), 3, 0),
    # un backfill manual a futuro respecto del mes que esté abierto
    ("hacia_adelante", (2026, 7), date(2026, 10, 1), 0, 2),
]


def correr_caso_ok(nombre, actual, objetivo, esperado_anterior, esperado_siguiente):
    calendario = CalendarioFalso(*actual)
    page = PageFalsa(calendario)
    navegar_a_mes(page, objetivo)
    ok = (
        calendario.anio == objetivo.year
        and calendario.mes_idx == objetivo.month - 1
        and calendario.clicks_anterior == esperado_anterior
        and calendario.clicks_siguiente == esperado_siguiente
    )
    estado = "OK" if ok else "FALLO"
    print(
        f"[{estado}] {nombre}: termino en mes_idx={calendario.mes_idx} anio={calendario.anio} "
        f"(clicks anterior={calendario.clicks_anterior}, siguiente={calendario.clicks_siguiente})"
    )
    return ok


def correr_caso_tope_de_seguridad():
    # Calendario "roto" que nunca cambia de mes al clickear — navegar_a_mes
    # debe darse por vencido con un error claro en vez de colgarse en un
    # loop infinito.
    calendario = CalendarioFalso(2026, 9, roto=True)
    page = PageFalsa(calendario)
    try:
        navegar_a_mes(page, date(2026, 9, 30))
        print("[FALLO] tope_de_seguridad: deberia haber lanzado RuntimeError")
        return False
    except RuntimeError:
        print("[OK] tope_de_seguridad: lanzo RuntimeError como se esperaba")
        return True


def correr_caso_estructura_distinta():
    # Si el picker cambia de estructura (ej. otro rediseño de LightData) y
    # los selectores ya no matchean nada, navegar_a_mes debe fallar rápido
    # y con un mensaje claro — no colgarse esperando 20s por un timeout.
    calendario = CalendarioFalso(2026, 9)
    calendario.existe = False
    page = PageFalsa(calendario)
    try:
        navegar_a_mes(page, date(2026, 9, 30))
        print("[FALLO] estructura_distinta: deberia haber lanzado RuntimeError")
        return False
    except RuntimeError:
        print("[OK] estructura_distinta: lanzo RuntimeError como se esperaba (falla rápido, no timeout)")
        return True


def main():
    resultados = [correr_caso_ok(*caso) for caso in CASOS_OK]
    resultados.append(correr_caso_tope_de_seguridad())
    resultados.append(correr_caso_estructura_distinta())

    if all(resultados):
        print(f"\n{len(resultados)}/{len(resultados)} casos OK.")
        sys.exit(0)
    else:
        fallidos = resultados.count(False)
        print(f"\n{fallidos} caso(s) fallaron.")
        sys.exit(1)


if __name__ == "__main__":
    main()
