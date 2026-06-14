"""Utilidades compartidas: cliente para la API CKAN del Portal Nacional de
Datos Abiertos del Perú (datosabiertos.gob.pe) y helpers de datos.

Particularidades del portal detectadas y manejadas aquí:
  * El portal corre sobre Drupal 7 con un CKAN detrás.
  * ``package_search`` (búsqueda por texto) NO funciona -> la búsqueda se
    implementa listando con ``package_list`` y filtrando localmente.
  * ``package_show`` devuelve ``result`` como una LISTA (no un dict).
  * Los CSV del MEF vienen en codificación latin-1 (cp1252).

Todas las funciones devuelven salidas PEQUEÑAS (metadatos, esquemas, muestras o
agregados), nunca datasets crudos completos (Regla 1 anti-flooding del HW).
"""
from __future__ import annotations

import csv
import functools
import io
import re
from decimal import Decimal
from pathlib import Path

import httpx

PORTAL = "https://www.datosabiertos.gob.pe"
API = f"{PORTAL}/api/3/action"
HEADERS = {"User-Agent": "mef-subnational-efficiency-mcp/0.1 (+local MCP)"}
TIMEOUT = httpx.Timeout(60.0, connect=20.0)


# --------------------------------------------------------------------------
#  Cliente HTTP / acciones CKAN
# --------------------------------------------------------------------------
def _client() -> httpx.Client:
    return httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)


def ckan_action(action: str, **params):
    """Llama a una acción de la API CKAN y devuelve el campo ``result``.

    Lanza ``RuntimeError`` si la API responde sin éxito.
    """
    with _client() as c:
        r = c.get(f"{API}/{action}", params=params or None)
        r.raise_for_status()
        data = r.json()
    if not data.get("success", False):
        raise RuntimeError(f"CKAN '{action}' falló: {data.get('error')}")
    return data["result"]


@functools.lru_cache(maxsize=1)
def _all_package_names() -> tuple[str, ...]:
    """Lista (cacheada) de los nombres de todos los datasets del portal."""
    return tuple(ckan_action("package_list"))


# --------------------------------------------------------------------------
#  Helpers de texto / serialización
# --------------------------------------------------------------------------
def strip_html(s: str) -> str:
    """Quita etiquetas HTML básicas de las descripciones del portal."""
    return re.sub(r"<[^>]+>", " ", s or "").replace("&nbsp;", " ").strip()


def _jsonable(v):
    """Convierte valores no serializables (Decimal, bytes, ...) a tipos JSON."""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    return str(v)


# --------------------------------------------------------------------------
#  Búsqueda y detalle de datasets
# --------------------------------------------------------------------------
def search_datasets(query: str, limit: int = 20) -> list[dict]:
    """Busca datasets por substring en el nombre (package_search está roto)."""
    q = query.lower().strip()
    hits = [n for n in _all_package_names() if q in n.lower()]
    return [{"slug": n} for n in hits[:limit]]


def get_dataset(slug: str) -> dict:
    """Metadatos de un dataset. En este portal ``package_show`` devuelve el
    result como lista -> lo normalizamos a dict."""
    res = ckan_action("package_show", id=slug)
    if isinstance(res, list):
        res = res[0] if res else {}
    return res or {}


def list_organizations(limit: int = 50) -> dict:
    """Entidades públicas registradas en el portal."""
    try:
        res = ckan_action("organization_list")
        res = list(res)
        return {"total": len(res), "entidades": res[:limit]}
    except Exception as e:  # noqa: BLE001 - degradación elegante
        return {"total": 0, "entidades": [], "nota": f"No disponible vía API: {e}"}


def list_groups(limit: int = 50) -> dict:
    """Grupos temáticos (categorías) de datasets."""
    try:
        res = ckan_action("group_list")
        res = list(res)
        return {"total": len(res), "categorias": res[:limit]}
    except Exception as e:  # noqa: BLE001
        return {"total": 0, "categorias": [], "nota": f"No disponible vía API: {e}"}


def recent_changes(limit: int = 10) -> dict:
    """Datasets modificados recientemente (cambios cronológicos)."""
    for action in ("recently_changed_packages_activity_list",
                   "current_package_list_with_resources"):
        try:
            res = ckan_action(action, limit=limit)
            items = []
            for it in (res or [])[:limit]:
                if isinstance(it, dict):
                    items.append({
                        "slug": it.get("name") or (it.get("data", {})
                                                   .get("package", {}).get("name")),
                        "modificado": it.get("metadata_modified") or it.get("timestamp"),
                    })
            if items:
                return {"total": len(items), "cambios": items}
        except Exception:  # noqa: BLE001
            continue
    return {"total": 0, "cambios": [], "nota": "No disponible vía API en este portal."}


# --------------------------------------------------------------------------
#  Inspección de CSV (anti-flooding) y descargas
# --------------------------------------------------------------------------
def fetch_csv_text(url: str, max_bytes: int | None = None) -> str:
    """Descarga (o muestrea con Range) un CSV remoto y lo decodifica latin-1."""
    headers = {"Range": f"bytes=0-{max_bytes}"} if max_bytes else {}
    with _client() as c:
        r = c.get(url, headers=headers)
        if r.status_code not in (200, 206):
            r.raise_for_status()
        return r.content.decode("latin-1", errors="replace")


def inspect_csv_schema(url: str, sample_rows: int = 5) -> dict:
    """Captura SOLO cabecera + unas pocas filas de un CSV remoto vía Range HTTP.

    Pieza central de la estrategia anti-flooding: no descarga el archivo entero.
    """
    text = fetch_csv_text(url, max_bytes=128 * 1024)  # 128 KB bastan
    reader = csv.reader(io.StringIO(text))
    rows = []
    for i, row in enumerate(reader):
        rows.append(row)
        if i >= sample_rows:
            break
    if not rows:
        return {"error": "No se pudo leer el CSV."}
    header = rows[0]
    sample = [r for r in rows[1:sample_rows + 1] if len(r) == len(header)]
    return {
        "url": url,
        "num_columnas": len(header),
        "columnas": header,
        "muestra": [{h: v for h, v in zip(header, r)} for r in sample],
        "nota": f"Cabecera + {len(sample)} filas (Range HTTP, anti-flooding).",
    }


def download_file(url: str, dest) -> dict:
    """Descarga un archivo a ``dest``. Detecta respuestas HTML (captcha)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with _client() as c:
        r = c.get(url)
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        dest.write_bytes(r.content)
    size = dest.stat().st_size
    ok = ("html" not in ctype.lower()) and size > 10_000
    return {
        "ruta": str(dest),
        "tamano_bytes": size,
        "content_type": ctype,
        "ok": ok,
        "nota": "" if ok else ("La respuesta parece HTML/captcha, no un archivo "
                               "válido. Descárgalo manualmente."),
    }


# --------------------------------------------------------------------------
#  Consultas tipo SQL con DuckDB (sobre CSV/Parquet, local o remoto)
# --------------------------------------------------------------------------
def duckdb_query(source: str, sql: str, limit: int = 50) -> dict:
    """Ejecuta SQL (DuckDB) sobre ``source`` usando el marcador ``{fuente}``.

    Siempre fuerza un LIMIT para no volcar datos crudos al contexto.
    """
    import duckdb

    if source.lower().endswith(".parquet"):
        ref = f"read_parquet('{source}')"
    else:
        ref = f"read_csv_auto('{source}', ignore_errors=true, sample_size=-1)"
    query = sql.replace("{fuente}", ref)
    if " limit " not in query.lower():
        query = query.rstrip().rstrip(";") + f" LIMIT {limit}"

    con = duckdb.connect()
    try:
        rel = con.sql(query)
        cols = list(rel.columns)
        rows = rel.fetchmany(limit)
    finally:
        con.close()
    return {
        "columnas": cols,
        "n_filas": len(rows),
        "filas": [{c: _jsonable(v) for c, v in zip(cols, r)} for r in rows],
        "nota": f"Salida limitada a {limit} filas (anti-flooding).",
    }
