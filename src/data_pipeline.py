"""Pipeline de ingesta del gasto público: descarga el CSV del MEF desde el
portal de datos abiertos, agrega con DuckDB y guarda salidas "microscópicas"
en Parquet. Streamlit luego lee SOLO esos Parquet (Regla 1 anti-flooding).

Uso por línea de comandos (Regla 2 — periodo dinámico)::

    py -3.12 src/data_pipeline.py 2025
    py -3.12 src/data_pipeline.py 2025-06     # devengado acumulado a junio

Funciones clave:
    procesar(periodo)         -> descarga + agrega + escribe Parquet (pesado)
    resumen_periodo(periodo)  -> lee el KPI ya procesado y lo resume (ligero;
                                 lo usa la herramienta MCP descargar_y_analizar)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import duckdb
import httpx
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analytical_engine as ae
import utils

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "data" / "snapshots"
PROCESSED = ROOT / "data" / "processed"
# El CSV crudo del MEF pesa GBs: se descarga a una carpeta temporal del SISTEMA
# (fuera de OneDrive y de git) para no sincronizarlo ni versionarlo.
RAW_CSV = Path(tempfile.gettempdir()) / "mef_subnational_raw_csv"

MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO",
         "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]

UMBRAL_HALL_OF_SHAME = 10_000_000  # PEN; unidades ejecutoras con PIM > 10M


# --------------------------------------------------------------------------
#  Localización / descarga del CSV
# --------------------------------------------------------------------------
def _parse_periodo(periodo: str) -> tuple[int, int | None]:
    """'2025' -> (2025, None);  '2025-06' -> (2025, 6)."""
    partes = str(periodo).split("-")
    anio = int(partes[0])
    mes = int(partes[1]) if len(partes) > 1 and partes[1] else None
    return anio, mes


def _csv_url(anio: int) -> str:
    """Encuentra la URL del CSV de gasto devengado mensual para el año dado."""
    hits = utils.search_datasets("devengado-mensual", limit=3)
    if not hits:
        raise RuntimeError("No se encontró el dataset de devengado en el portal.")
    detalle = utils.get_dataset(hits[0]["slug"])
    recursos = detalle.get("resources", [])
    preferidos = [r.get("url", "") for r in recursos
                  if f"{anio}-Gasto-Devengado-Mensual" in r.get("url", "")]
    cualquiera = [r.get("url", "") for r in recursos
                  if f"{anio}-Gasto-Devengado" in r.get("url", "")
                  and r.get("url", "").lower().endswith(".csv")]
    url = (preferidos or cualquiera or [None])[0]
    if not url:
        raise RuntimeError(f"No se encontró CSV de gasto para el año {anio}.")
    return url


def _descargar_raw(url: str, raw: Path, reintentos: int = 20) -> None:
    """Descarga los bytes crudos de ``url`` a ``raw`` de forma REANUDABLE.

    Una descarga de varios GB en una sola conexión suele estancarse; aquí se
    reanuda con HTTP Range desde el último byte recibido y se reintenta ante
    cortes o timeouts. Trabaja sobre bytes crudos (no convertidos) para que el
    offset de Range coincida exactamente con el archivo.
    """
    # Tamaño total esperado (Content-Length).
    with httpx.Client(headers=utils.HEADERS, timeout=httpx.Timeout(30.0),
                      follow_redirects=True) as c:
        total = int(c.head(url).headers.get("content-length", 0))

    timeout = httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0)
    for intento in range(reintentos):
        have = raw.stat().st_size if raw.exists() else 0
        if total and have >= total:
            return
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with httpx.Client(headers={**utils.HEADERS, **headers},
                              timeout=timeout, follow_redirects=True) as c:
                with c.stream("GET", url) as r:
                    r.raise_for_status()
                    with open(raw, "ab") as f:
                        for chunk in r.iter_bytes(chunk_size=1 << 20):
                            f.write(chunk)
        except (httpx.HTTPError, OSError) as e:
            print(f"  [descarga] corte en intento {intento + 1} "
                  f"({raw.stat().st_size/1e9:.2f} GB): {type(e).__name__}; reanudando...",
                  flush=True)
            continue
    final = raw.stat().st_size if raw.exists() else 0
    if total and final < total:
        raise RuntimeError(f"Descarga incompleta: {final}/{total} bytes tras "
                           f"{reintentos} reintentos.")


def _descargar_csv(anio: int) -> Path:
    """Devuelve el CSV anual (UTF-8) en RAW_CSV, descargándolo de forma robusta.

    Estrategia: descarga cruda reanudable -> conversión latin-1→UTF-8 -> CSV.
    Reutiliza archivos ya presentes para no rebajar nada.
    """
    RAW_CSV.mkdir(parents=True, exist_ok=True)
    destino = RAW_CSV / f"{anio}-Gasto-Devengado.csv"
    if destino.exists() and destino.stat().st_size > 1_000_000:
        return destino

    url = _csv_url(anio)
    raw = RAW_CSV / f"{anio}-Gasto-Devengado.raw"
    print("  [descarga] obteniendo CSV crudo (reanudable)...", flush=True)
    _descargar_raw(url, raw)

    # Conversión latin-1 -> UTF-8 (1 byte por carácter: seguro por chunks).
    print("  [conversion] latin-1 -> UTF-8 ...", flush=True)
    with open(raw, "rb") as ent, open(destino, "w", encoding="utf-8", newline="") as sal:
        while True:
            chunk = ent.read(1 << 20)
            if not chunk:
                break
            sal.write(chunk.decode("latin-1"))
    raw.unlink(missing_ok=True)
    return destino


# --------------------------------------------------------------------------
#  Agregaciones DuckDB -> DataFrames
# --------------------------------------------------------------------------
def _dev_expr(mes: int | None) -> str:
    """Expresión SQL del devengado: anual o acumulado hasta el mes dado."""
    if mes is None:
        return "COALESCE(TRY_CAST(MONTO_DEVENGADO_ANUAL AS DOUBLE), 0)"
    cols = MESES[:mes]
    return " + ".join(f"COALESCE(TRY_CAST(MONTO_DEVENGADO_{m} AS DOUBLE), 0)"
                      for m in cols)


def _vista(con: duckdb.DuckDBPyConnection, csv_path: Path, mes: int | None) -> None:
    """Crea una vista 'gasto' con las columnas relevantes ya tipadas.

    Lee el CSV como texto (all_varchar) y castea con TRY_CAST para tolerar el
    formato latin-1 y los valores citados del MEF.
    """
    path = csv_path.as_posix()
    con.execute(f"""
        CREATE OR REPLACE VIEW gasto AS
        SELECT
            DEPARTAMENTO_EJECUTORA_NOMBRE              AS departamento,
            NIVEL_GOBIERNO_NOMBRE                      AS nivel_gobierno,
            SECTOR_NOMBRE                              AS sector,
            PLIEGO_NOMBRE                              AS pliego,
            EJECUTORA_NOMBRE                           AS unidad_ejecutora,
            COALESCE(TRY_CAST(MONTO_PIM AS DOUBLE), 0) AS pim,
            COALESCE(TRY_CAST(MONTO_PIA AS DOUBLE), 0) AS pia,
            {_dev_expr(mes)}                           AS devengado
        FROM read_csv('{path}', header=true, all_varchar=true,
                      encoding='utf-8', delim=',', quote='"', escape='"',
                      strict_mode=false, null_padding=true,
                      ignore_errors=true, max_line_size=10000000)
    """)


def _agg(con, group_cols: list[str], having: str = "") -> pd.DataFrame:
    cols = ", ".join(group_cols)
    sql = f"""
        SELECT {cols},
               SUM(pim) AS pim,
               SUM(devengado) AS devengado
        FROM gasto
        GROUP BY {cols}
        {having}
    """
    return con.execute(sql).df()


def _serie_mensual(con, csv_path: Path) -> pd.DataFrame:
    path = csv_path.as_posix()
    sums = ", ".join(
        f"SUM(COALESCE(TRY_CAST(MONTO_DEVENGADO_{m} AS DOUBLE), 0)) AS {m}"
        for m in MESES
    )
    row = con.execute(f"""
        SELECT {sums}
        FROM read_csv('{path}', header=true, all_varchar=true,
                      encoding='utf-8', delim=',', quote='"', escape='"',
                      strict_mode=false, null_padding=true,
                      ignore_errors=true, max_line_size=10000000)
    """).df().iloc[0]
    return pd.DataFrame({"mes": MESES, "devengado": [float(row[m]) for m in MESES]})


# --------------------------------------------------------------------------
#  Orquestación
# --------------------------------------------------------------------------
def _snapshot(csv_path: Path, anio: int) -> Path:
    """Guarda un snapshot del esquema (cabecera + 5 filas) en data/snapshots/."""
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    # Leemos localmente las primeras filas (rápido, sin red).
    import csv as _csv
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = _csv.reader(f)
        filas = [next(reader)]
        for _ in range(5):
            try:
                filas.append(next(reader))
            except StopIteration:
                break
    header = filas[0]
    muestra = [dict(zip(header, r)) for r in filas[1:]]
    destino = SNAPSHOTS / f"esquema_{anio}.json"
    destino.write_text(json.dumps(
        {"num_columnas": len(header), "columnas": header, "muestra": muestra},
        ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


def procesar(periodo: str = "2025") -> dict:
    """Descarga el CSV del periodo, agrega con DuckDB y escribe Parquet.

    Devuelve un resumen pequeño (KPIs nacionales + rutas/conteos generados).
    """
    anio, mes = _parse_periodo(periodo)
    PROCESSED.mkdir(parents=True, exist_ok=True)

    csv_path = _descargar_csv(anio)
    snap = _snapshot(csv_path, anio)

    con = duckdb.connect()
    try:
        _vista(con, csv_path, mes)

        # KPIs nacionales
        kpi = con.execute(
            "SELECT SUM(pim) AS pim, SUM(devengado) AS devengado FROM gasto"
        ).df()
        pim_tot = float(kpi["pim"][0] or 0)
        dev_tot = float(kpi["devengado"][0] or 0)
        kpis = pd.DataFrame([{
            "periodo": periodo,
            "pim": pim_tot,
            "devengado": dev_tot,
            "saldo_no_devengado": ae.saldo_no_devengado(pim_tot, dev_tot),
            "avance_pct": round(ae.avance(dev_tot, pim_tot), 2),
        }])

        # Por departamento
        dep = ae.agregar_metricas(_agg(con, ["departamento"]))
        dep = dep.sort_values("pim", ascending=False)

        # Por sector
        sec = ae.agregar_metricas(_agg(con, ["sector"])).sort_values("pim", ascending=False)

        # Hall of Shame: unidades ejecutoras con PIM > 10M, peor avance primero
        ue = ae.agregar_metricas(
            _agg(con, ["pliego", "unidad_ejecutora", "departamento"],
                 having=f"HAVING SUM(pim) > {UMBRAL_HALL_OF_SHAME}")
        ).sort_values("avance_pct", ascending=True)

        # Serie mensual nacional
        serie = _serie_mensual(con, csv_path)
    finally:
        con.close()

    salidas = {
        f"kpis_{anio}.parquet": kpis,
        f"departamentos_{anio}.parquet": dep,
        f"sectores_{anio}.parquet": sec,
        f"unidades_ejecutoras_{anio}.parquet": ue,
        f"devengado_mensual_{anio}.parquet": serie,
    }
    for nombre, df in salidas.items():
        df.to_parquet(PROCESSED / nombre, index=False)

    return {
        "periodo": periodo,
        "kpis_nacionales": {
            "pim": pim_tot,
            "devengado": dev_tot,
            "saldo_no_devengado": pim_tot - dev_tot,
            "avance_pct": round(ae.avance(dev_tot, pim_tot), 2),
        },
        "departamentos": int(len(dep)),
        "unidades_hall_of_shame": int(len(ue)),
        "snapshot": str(snap.relative_to(ROOT)),
        "archivos_parquet": list(salidas.keys()),
    }


def resumen_periodo(periodo: str = "2025") -> dict:
    """Lectura LIGERA del KPI ya procesado (la usa la herramienta MCP).

    No descarga ni reprocesa; si el Parquet no existe, sugiere ejecutar el
    pipeline.
    """
    anio, _ = _parse_periodo(periodo)
    kpi_path = PROCESSED / f"kpis_{anio}.parquet"
    if not kpi_path.exists():
        return {"estado": "pendiente",
                "detalle": f"Ejecuta el pipeline: py -3.12 src/data_pipeline.py {anio}"}
    fila = pd.read_parquet(kpi_path).iloc[0].to_dict()
    return {"estado": "ok", "kpis_nacionales": fila}


if __name__ == "__main__":
    periodo = sys.argv[1] if len(sys.argv) > 1 else "2025"
    print(f"[pipeline] procesando periodo {periodo} ...")
    resumen = procesar(periodo)
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
