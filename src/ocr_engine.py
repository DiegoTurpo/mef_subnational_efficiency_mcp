"""Motor OCR para los documentos históricos de 1964.

Rasteriza el PDF página por página con PyMuPDF (memory caps) y aplica
PaddleOCR sobre 15+ páginas, cacheando los resultados.

Se implementa en el branch feature/historical-1964-paddle-ocr.
"""
from __future__ import annotations


def procesar(nombre_pdf: str = "cuenta_general_1964.pdf", paginas: int = 15) -> dict:
    """Procesa N páginas del PDF de 1964 y devuelve un resumen de la extracción."""
    raise NotImplementedError
