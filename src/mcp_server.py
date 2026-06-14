"""Servidor MCP local para auditar el gasto público del Perú.

Expone 10 herramientas que el agente (Claude Code) usa para interactuar con el
Portal Nacional de Datos Abiertos (datosabiertos.gob.pe) y con la
infraestructura local del proyecto (OCR, agregaciones).

Diseño anti-context-flooding (Regla 1 del HW): NINGUNA herramienta devuelve
datasets crudos completos — solo metadatos, esquemas, muestras pequeñas o
resultados ya agregados.

Ejecutar (transporte stdio, sin autenticación privilegiada):
    py -3.12 src/mcp_server.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Permitir importar módulos hermanos (utils, ocr_engine, ...) al correr directo.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP

import utils

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

mcp = FastMCP("mef-subnational-efficiency")


# 1 ────────────────────────────────────────────────────────────────────────
@mcp.tool()
def buscar_datasets(consulta: str, limite: int = 15) -> list[dict]:
    """Busca datasets en el portal por coincidencia de texto en su nombre.

    El ``package_search`` del portal está deshabilitado, así que la búsqueda
    lista todos los datasets y filtra localmente. Devuelve solo los slugs.
    """
    return utils.search_datasets(consulta, limit=limite)


# 2 ────────────────────────────────────────────────────────────────────────
@mcp.tool()
def obtener_detalle_dataset(slug: str) -> dict:
    """Metadatos de un dataset y las URLs de sus recursos (sin datos crudos).

    Útil para localizar el CSV de un año concreto, p.ej. el recurso
    ``2025-Gasto-Devengado-Mensual.csv``.
    """
    d = utils.get_dataset(slug)
    if not d:
        return {"error": f"No se encontró el dataset '{slug}'"}
    recursos = [
        {
            "nombre": r.get("name") or utils.strip_html(r.get("description", ""))[:60],
            "formato": r.get("format"),
            "url": r.get("url"),
        }
        for r in d.get("resources", [])
    ]
    return {
        "slug": d.get("name"),
        "titulo": d.get("title"),
        "organizacion": (d.get("organization") or {}).get("title"),
        "descripcion": utils.strip_html(d.get("notes", ""))[:400],
        "num_recursos": len(recursos),
        "recursos": recursos,
    }


# 3 ────────────────────────────────────────────────────────────────────────
@mcp.tool()
def descargar_documento_1964(url: str,
                             nombre_archivo: str = "cuenta_general_1964.pdf") -> dict:
    """Descarga un PDF histórico a ``data/raw_pdfs/`` y devuelve ruta y tamaño.

    No procesa el PDF (de eso se encarga ``procesar_ocr_paginas_1964``).
    Nota: Google Books bloquea descargas automáticas con captcha; si la
    respuesta es HTML, descárgalo manualmente.
    """
    destino = DATA / "raw_pdfs" / nombre_archivo
    return utils.download_file(url, destino)


# 4 ────────────────────────────────────────────────────────────────────────
@mcp.tool()
def listar_entidades_publicas(limite: int = 50) -> dict:
    """Lista las organizaciones/entidades públicas registradas en el portal."""
    return utils.list_organizations(limit=limite)


# 5 ────────────────────────────────────────────────────────────────────────
@mcp.tool()
def listar_categorias_tematicas(limite: int = 50) -> dict:
    """Lista los grupos temáticos (categorías) de datasets del portal."""
    return utils.list_groups(limit=limite)


# 6 ────────────────────────────────────────────────────────────────────────
@mcp.tool()
def obtener_ultimas_actualizaciones(limite: int = 10) -> dict:
    """Devuelve datasets modificados recientemente (cambios cronológicos)."""
    return utils.recent_changes(limit=limite)


# 7 ────────────────────────────────────────────────────────────────────────
@mcp.tool()
def inspeccionar_esquema_csv(url: str, filas_muestra: int = 5) -> dict:
    """Captura SOLO la cabecera y unas pocas filas de un CSV remoto.

    Pieza central de la estrategia anti-flooding: usa un Range HTTP para no
    descargar el archivo completo. Devuelve columnas + muestra mínima.
    """
    return utils.inspect_csv_schema(url, sample_rows=filas_muestra)


# 8 ────────────────────────────────────────────────────────────────────────
@mcp.tool()
def consultar_datastore_filtrado(fuente: str, sql: str, limite: int = 50) -> dict:
    """Ejecuta una consulta tipo SQL (DuckDB) sobre un CSV/Parquet y devuelve
    como máximo ``limite`` filas. ``fuente`` puede ser ruta local o URL.

    Usa el marcador ``{fuente}`` en el SQL, por ejemplo::

        SELECT DEPARTAMENTO_EJECUTORA_NOMBRE, SUM(MONTO_PIM) AS pim
        FROM {fuente} GROUP BY 1 ORDER BY pim DESC

    Se fuerza un LIMIT para no volcar datos crudos al contexto (Regla 1).
    """
    return utils.duckdb_query(fuente, sql, limit=limite)


# 9 ────────────────────────────────────────────────────────────────────────
@mcp.tool()
def procesar_ocr_paginas_1964(nombre_pdf: str = "cuenta_general_1964.pdf",
                              paginas: int = 15) -> dict:
    """Dispara el motor OCR (PaddleOCR) sobre N páginas del PDF de 1964.

    La implementación vive en ``ocr_engine.py`` (branch
    feature/historical-1964-paddle-ocr).
    """
    try:
        import ocr_engine
        return ocr_engine.procesar(nombre_pdf=nombre_pdf, paginas=paginas)
    except NotImplementedError:
        return {"estado": "pendiente",
                "detalle": "ocr_engine se implementa en el branch de OCR (1964)."}


# 10 ───────────────────────────────────────────────────────────────────────
@mcp.tool()
def descargar_y_analizar_estadisticas(periodo: str = "2025") -> dict:
    """Ejecuta el pipeline local (descarga + DuckDB) y devuelve un resumen
    agregado y pequeño (no los datos crudos).

    La implementación vive en ``data_pipeline.py`` (branch
    feature/data-snapshot-pipeline).
    """
    try:
        import data_pipeline
        return data_pipeline.resumen_periodo(periodo)
    except NotImplementedError:
        return {"estado": "pendiente",
                "detalle": "data_pipeline se implementa en el branch del pipeline."}


if __name__ == "__main__":
    mcp.run()
