"""
Script de PRUEBA, fuera del pipeline de producción: sube el export crudo de
LightData "tal cual" a Supabase (tabla `envios`), para validar el diseño de
la base nueva antes de migrar el dashboard y `descarga_diaria.yml` de
verdad (ver reglas_de_negocio.md, sección sobre el ecosistema Supabase).

No toca Firestore ni ningún script de producción existente. Corre contra un
proyecto de Supabase separado, usando las credenciales en `scripts/.env`
(ver requirements_supabase.txt para las dependencias extra que necesita,
no incluidas en requirements.txt porque todavía no corre en CI).

Uso: python publicar_supabase.py <archivo_crudo.xls>
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, str(Path(__file__).parent))
from generar_reporte import cargar_export  # noqa: E402  (reusa la lectura ya resuelta del .xls)

LOTE = 500


def normalizar_id(valor) -> str | None:
    """'1034944.0' (float de pandas) -> '1034944'. Nunca se asume que viene
    como string limpio: Excel/pandas puede leer una columna numérica como
    float aunque LightData la muestre sin decimales."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    try:
        return str(int(float(valor)))
    except (TypeError, ValueError):
        texto = str(valor).strip()
        return texto or None


def texto_o_none(valor) -> str | None:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    texto = str(valor).strip()
    return texto or None


def parsear_fecha(valor) -> str | None:
    """Acepta 'dd/mm/yyyy HH:MM' o 'dd/mm/yyyy' (formato real de LightData,
    ver diccionario_de_datos.md) y devuelve ISO 8601 con offset -03:00.

    LightData entrega estas fechas en hora de Argentina (ART = UTC-3 fijo,
    sin horario de verano, mismo criterio que el resto del proyecto — ver
    reglas_de_negocio.md) pero SIN indicarlo: el valor crudo es un
    datetime "naive". Si se manda tal cual a una columna timestamptz,
    Postgres lo toma como UTC y el resultado queda 3 horas adelantado
    (bug real detectado 2026-11-15 antes de usar estas columnas para el
    corte de las 21hs) — por eso acá se agrega el offset explícito.
    """
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, str) and not valor.strip():
        return None
    dt = pd.to_datetime(valor, dayfirst=True, errors="coerce")
    if pd.isna(dt):
        return None
    return dt.isoformat() + "-03:00"


def valor_json_seguro(valor):
    """Convierte tipos de numpy/pandas a algo serializable por el cliente
    de Supabase (json estándar) antes de meterlo en la columna `raw`."""
    if valor is None:
        return None
    if isinstance(valor, float) and pd.isna(valor):
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.isoformat()
    if isinstance(valor, np.integer):
        return int(valor)
    if isinstance(valor, np.floating):
        return float(valor)
    if isinstance(valor, np.bool_):
        return bool(valor)
    return valor


def construir_filas(df: pd.DataFrame) -> list[dict]:
    filas = []
    for _, fila in df.iterrows():
        id_interno = normalizar_id(fila.get("ID (Interno)"))
        if not id_interno:
            continue  # misma regla que cargar_export: sin ID (Interno) no es un envío real

        fecha_mp_iso = parsear_fecha(fila.get("Fecha MercadoPacks"))
        filas.append({
            "id_interno": id_interno,
            "tracking": texto_o_none(fila.get("Número Tracking")),
            "cliente": texto_o_none(fila.get("Nombre Fantasia")),
            "localidad": texto_o_none(fila.get("Localidad")),
            "zona": texto_o_none(fila.get("Zona")),
            "estado": texto_o_none(fila.get("Estado")),
            # Promovidas desde el raw (ver diccionario_de_datos.md: ninguna de
            # las dos viene estandarizada) para que el módulo de
            # Fallidos/Cambios pueda filtrarlas sin tener que parsear jsonb en
            # cada consulta — el Estado de Lightdata no define un Cambio
            # (describe el paquete NUEVO entregado, no si el chofer ya trajo
            # el original), así que la señal real es Logistica Inversa /
            # Observaciones.
            "logistica_inversa": texto_o_none(fila.get("Logistica Inversa")),
            "observaciones": texto_o_none(fila.get("Observaciones")),
            "cadete": texto_o_none(fila.get("Cadete")),
            "fecha_mercadopacks": fecha_mp_iso[:10] if fecha_mp_iso else None,
            "fecha_estado": parsear_fecha(fila.get("Fecha estado")),
            "fecha_asignacion": parsear_fecha(fila.get("Fecha de asignación")),
            "fecha_a_planta": parsear_fecha(fila.get("Fecha a planta")),
            "raw": {str(k): valor_json_seguro(v) for k, v in fila.items()},
        })
    return filas


def main():
    if len(sys.argv) < 2:
        sys.exit("Uso: publicar_supabase.py <archivo_crudo.xls>")

    ruta = Path(sys.argv[1])
    if not ruta.exists():
        sys.exit(f"No se encontró el archivo: {ruta}")

    load_dotenv(Path(__file__).parent / ".env")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("Faltan SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY (ver scripts/.env)")

    print(f"Leyendo {ruta} ...")
    df = cargar_export(ruta)
    print(f"{len(df)} filas en el export crudo.")

    filas = construir_filas(df)
    print(f"{len(filas)} filas válidas (con ID (Interno)) para subir a Supabase.")
    if not filas:
        sys.exit("Nada para subir.")

    client = create_client(url, key)
    for i in range(0, len(filas), LOTE):
        lote = filas[i:i + LOTE]
        client.table("envios").upsert(lote, on_conflict="id_interno").execute()
        print(f"  subidas {min(i + LOTE, len(filas))}/{len(filas)}")

    print("Listo.")


if __name__ == "__main__":
    main()
