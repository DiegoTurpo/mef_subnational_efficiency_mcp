"""Pipeline de ingesta del gasto 2025: descarga el CSV del MEF, agrega con
DuckDB y guarda salidas "microscópicas" en Parquet (Regla 1 anti-flooding).

Se implementa en el branch feature/data-snapshot-pipeline.
"""
from __future__ import annotations


def resumen_periodo(periodo: str = "2025") -> dict:
    """Descarga + procesa el periodo indicado y devuelve un resumen agregado."""
    raise NotImplementedError
