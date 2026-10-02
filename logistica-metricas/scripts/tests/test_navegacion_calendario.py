#!/usr/bin/env python3
"""
test_navegacion_calendario.py
-------------------------------
Prueba de regresión para `navegar_a_mes()` (en `descargar_lightdata.py`),
sin depender de LightData ni de un navegador real.

Incidente real que esto corrige (2026-10-01): `seleccionar_dia()` clickeaba
el número de día en el mes que el calendario de LightData (un date picker de
Angular Material) tuviera abierto por default, sin navegar. La corrida de
cierre de las 00hs ART del 1° de octubre pidió los días 30/29/28 de
SEPTIEMBRE, pero el calendario abría en OCTUBRE — y como esos números de día
también existen en octubre, clickeó la fecha equivocada sin ningún error
visible. LightData devolvió 0 filas y el snapshot de esos 3 días quedó sin
actualizar, EN SILENCIO (el workflow de GitHub Actions marcó esa corrida
como exitosa).

En vez de un fixture HTML con el componente real de Angular Material (mucho
más pesado de vendorizar que Select2), esta prueba usa un "calendario falso"
en Python que simula únicamente el contrato que `navegar_a_mes()` necesita:
leer la etiqueta del período actual (`mat-calendar-period-button`) y
clickear anterior/siguiente — exactamente el mismo patrón de "probar la
lógica real contra un doble simple" que ya se usa en este proyecto.

Uso:
    cd logistica-metricas/scripts/tests
    python3 test_navegacion_calendario.py

Sale con código 0 si todos los casos pasan, 1 si alguno falla.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from descargar_lightdata import navegar_a_mes, MESES_ES  # noqa: E402


class CalendarioFalso:
    """Simula el estado interno del date picker: un mes/año actual que
    cambia cuando se clickea anterior/siguiente."""

    def __init__(self, anio: int, mes: int, roto: bool = False):
        self.anio = anio
        self.mes = mes  # 1-12
        self.roto = roto  # si True, los botones no cambian nada (para probar el tope de seguridad)
        self.clicks_anterior = 0
        self.clicks_siguiente = 0

    def etiqueta(self) -> str:
        return f"{MESES_ES[self.mes - 1]} {self.anio}"

    def mes_anterior(self):
        self.clicks_anterior += 1
        if self.roto:
            return
        self.mes -= 1
        if self.mes == 0:
            self.mes = 12
            self.anio -= 1

    def mes_siguiente(self):
        self.clicks_siguiente += 1
        if self.roto:
            return
        self.mes += 1
        if self.mes == 13:
            self.mes = 1
            self.anio += 1


class LocatorFalso:
    def __init__(self, calendario: CalendarioFalso, kind: str):
        self.calendario = calendario
        self.kind = kind

    def inner_text(self):
        assert self.kind == "period"
        return self.calendario.etiqueta()

    def click(self):
        if self.kind == "prev":
            self.calendario.mes_anterior()
        elif self.kind == "next":
            self.calendario.mes_siguiente()
        else:
            raise AssertionError("no se debería clickear el botón de período")


class PageFalsa:
    def __init__(self, calendario: CalendarioFalso):
        self.calendario = calendario

    def locator(self, selector: str):
        if "previous" in selector:
            return LocatorFalso(self.calendario, "prev")
        if "next" in selector:
            return LocatorFalso(self.calendario, "next")
        if "period" in selector:
            return LocatorFalso(self.calendario, "period")
        raise AssertionError(f"selector inesperado: {selector}")


CASOS_OK = [
    # (nombre, año/mes actual del calendario, fecha objetivo, clicks "anterior" esperados, clicks "siguiente" esperados)
    ("ya_esta_en_el_mes_correcto", (2026, 9), date(2026, 9, 30), 0, 0),
    # el incidente real: calendario en octubre, se pide un día de septiembre
    ("un_mes_atras_mismo_anio", (2026, 10), date(2026, 9, 30), 1, 0),
    ("tres_meses_atras", (2026, 12), date(2026, 9, 28), 3, 0),
    # cruce de año hacia atrás (ej. corrida de cierre del 1° de enero)
    ("cruce_de_anio_atras", (2027, 1), date(2026, 10, 15), 3, 0),
    # un backfill manual a futuro respecto del mes que esté abierto
    ("hacia_adelante", (2026, 8), date(2026, 10, 1), 0, 2),
]


def correr_caso_ok(nombre, actual, objetivo, esperado_anterior, esperado_siguiente):
    calendario = CalendarioFalso(*actual)
    page = PageFalsa(calendario)
    navegar_a_mes(page, objetivo)
    ok = (
        calendario.anio == objetivo.year
        and calendario.mes == objetivo.month
        and calendario.clicks_anterior == esperado_anterior
        and calendario.clicks_siguiente == esperado_siguiente
    )
    estado = "OK" if ok else "FALLÓ"
    print(
        f"[{estado}] {nombre}: terminó en {calendario.etiqueta()} "
        f"(clicks anterior={calendario.clicks_anterior}, siguiente={calendario.clicks_siguiente})"
    )
    return ok


def correr_caso_tope_de_seguridad():
    # Calendario "roto" que nunca cambia de mes al clickear — navegar_a_mes
    # debe darse por vencido con un error claro en vez de colgarse en un
    # loop infinito.
    calendario = CalendarioFalso(2026, 10, roto=True)
    page = PageFalsa(calendario)
    try:
        navegar_a_mes(page, date(2026, 9, 30))
        print("[FALLÓ] tope_de_seguridad: debería haber lanzado RuntimeError")
        return False
    except RuntimeError:
        print("[OK] tope_de_seguridad: lanzó RuntimeError como se esperaba")
        return True


def main():
    resultados = [correr_caso_ok(*caso) for caso in CASOS_OK]
    resultados.append(correr_caso_tope_de_seguridad())

    if all(resultados):
        print(f"\n{len(resultados)}/{len(resultados)} casos OK.")
        sys.exit(0)
    else:
        fallidos = resultados.count(False)
        print(f"\n{fallidos} caso(s) fallaron.")
        sys.exit(1)


if __name__ == "__main__":
    main()
