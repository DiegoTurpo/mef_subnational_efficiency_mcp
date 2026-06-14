"""Motor OCR para la Cuenta General de la República de 1964.

Rasteriza páginas del PDF con PyMuPDF (página por página, controlando memoria)
y aplica PaddleOCR sobre 15+ páginas. Usa las coordenadas de cada texto para
reconstruir las filas de las matrices financieras (concepto a la izquierda,
montos a la derecha), computa resúmenes y deja datos listos para los gráficos
históricos del Tab 1. Cachea el OCR por página (JSON con texto + posición) para
no reprocesar.

Uso por línea de comandos::

    py -3.12 src/ocr_engine.py                 # 15 páginas desde la 57
    py -3.12 src/ocr_engine.py 5 57            # 5 páginas desde la 57 (por tandas)
"""
from __future__ import annotations

import json
import os
import re
import statistics
import sys
from pathlib import Path

# Desactiva oneDNN: PaddlePaddle 3.x lanza un NotImplementedError en oneDNN al
# ejecutar la inferencia en CPU. Debe fijarse ANTES de importar paddle.
os.environ.setdefault("FLAGS_use_mkldnn", "0")

import fitz  # PyMuPDF
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PDF_DEFECTO = DATA / "raw_pdfs" / "cuenta_general_1964.pdf"
OCR_CACHE = DATA / "ocr_cache"
PROCESSED = DATA / "processed"

# Bloque de 15 páginas contiguas con matrices financieras densas (todas con
# contenido), seleccionado analizando la densidad de cifras del documento.
PAGINA_INICIO_DEFECTO = 664
DPI = 200

# Montos históricos: "4'659,628.92" (apóstrofo=millones, coma=miles, .dd=decimal).
# Solo tratamos como monto los tokens con decimales .dd (descarta números de ley).
_RE_MONTO = re.compile(r"\d[\d',]*\.\d{2}")

_OCR = None


# --------------------------------------------------------------------------
#  PaddleOCR (carga perezosa)
# --------------------------------------------------------------------------
def _get_ocr():
    """Inicializa PaddleOCR (perezoso). Desactiva oneDNN y los modelos de
    orientación/desdoblado (no necesarios aquí y fuente de fallos en CPU)."""
    global _OCR
    if _OCR is None:
        from paddleocr import PaddleOCR
        opciones = dict(lang="es", enable_mkldnn=False,
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_textline_orientation=False)
        try:
            _OCR = PaddleOCR(**opciones)
        except (TypeError, ValueError):
            _OCR = PaddleOCR(lang="es")
    return _OCR


def _ocr_items(img) -> list[dict]:
    """Devuelve [{texto, x, y, h}] con el texto y su posición (API 3.x)."""
    ocr = _get_ocr()
    items: list[dict] = []
    for r in ocr.predict(img) or []:
        get = r.get if hasattr(r, "get") else (lambda k, d=None: getattr(r, k, d))
        textos = get("rec_texts") or []
        cajas = get("rec_boxes")
        if cajas is None:
            polys = get("rec_polys") or get("dt_polys") or []
            cajas = []
            for p in polys:
                pts = p.tolist() if hasattr(p, "tolist") else p
                xs = [pt[0] for pt in pts]
                ys = [pt[1] for pt in pts]
                cajas.append([min(xs), min(ys), max(xs), max(ys)])
        for t, b in zip(textos, cajas):
            b = b.tolist() if hasattr(b, "tolist") else list(b)
            x1, y1, _x2, y2 = float(b[0]), float(b[1]), float(b[2]), float(b[3])
            items.append({"texto": t, "x": x1, "y": y1, "h": max(1.0, y2 - y1)})
    return items


# --------------------------------------------------------------------------
#  Rasterizado y parsing espacial
# --------------------------------------------------------------------------
def _render(doc, idx: int, dpi: int = DPI):
    """Rasteriza una página a un arreglo numpy BGR (para PaddleOCR/OpenCV)."""
    import numpy as np
    pix = doc[idx].get_pixmap(dpi=dpi)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:        # RGBA -> RGB
        img = img[:, :, :3]
    return img[:, :, ::-1].copy()  # RGB -> BGR


def _monto(tok: str) -> float:
    return float(tok.replace("'", "").replace(",", ""))


def _extraer_montos(items: list[dict]) -> list[float]:
    """Extrae TODAS las cifras monetarias de una página (lo más fiable del OCR)."""
    montos = []
    for it in items:
        for m in _RE_MONTO.findall(it.get("texto", "")):
            v = _monto(m)
            if v > 0:
                montos.append(v)
    return montos


def _extraer_conceptos(items: list[dict]) -> list[dict]:
    """Best-effort: empareja conceptos (texto) con montos por fila (posición).

    La calidad depende del escaneo de 1964; se filtra para quedarnos solo con
    conceptos legibles (varias palabras con letras). Es un extra, no la base del
    análisis (que se apoya en las cifras de ``_extraer_montos``).
    """
    if not items:
        return []
    tol = max(8.0, statistics.median(it["h"] for it in items) * 0.6)
    items = sorted(items, key=lambda d: d["y"])

    grupos, grupo, yref = [], [items[0]], items[0]["y"]
    for it in items[1:]:
        if abs(it["y"] - yref) <= tol:
            grupo.append(it)
        else:
            grupos.append(grupo)
            grupo, yref = [it], it["y"]
    grupos.append(grupo)

    conceptos = []
    for g in grupos:
        texto, montos = [], []
        for it in sorted(g, key=lambda d: d["x"]):
            t = (it["texto"] or "").strip()
            ms = _RE_MONTO.findall(t)
            resto = _RE_MONTO.sub("", t).strip(" .-")
            if ms:
                montos.extend(_monto(m) for m in ms)
            if sum(c.isalpha() for c in resto) >= 3:
                texto.append(resto)
        nombre = " ".join(texto).strip()
        # Solo conceptos legibles: >= 8 letras y al menos dos palabras.
        if montos and sum(c.isalpha() for c in nombre) >= 8 and " " in nombre:
            conceptos.append({"concepto": nombre, "monto": max(montos)})
    return conceptos


# --------------------------------------------------------------------------
#  Orquestación
# --------------------------------------------------------------------------
def procesar(nombre_pdf: str = "cuenta_general_1964.pdf",
             paginas: int = 15,
             inicio: int = PAGINA_INICIO_DEFECTO) -> dict:
    """Procesa ``paginas`` páginas desde ``inicio`` con PaddleOCR.

    Genera Parquet con conceptos/montos y un resumen JSON, y cachea el OCR por
    página (JSON). Devuelve un resumen pequeño. Es reanudable gracias a la caché.
    """
    pdf = DATA / "raw_pdfs" / nombre_pdf
    if not pdf.exists():
        return {"error": f"No se encontró el PDF en {pdf}. Descárgalo primero."}

    OCR_CACHE.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf)
    inicio = max(1, inicio)
    fin = min(inicio + paginas - 1, doc.page_count)

    montos_all, conceptos_all, por_pagina = [], [], []
    for n in range(inicio, fin + 1):
        cache = OCR_CACHE / f"1964_pag_{n:04d}.json"
        if cache.exists():
            items = json.loads(cache.read_text(encoding="utf-8"))
        else:
            items = _ocr_items(_render(doc, n - 1))
            cache.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")

        montos = _extraer_montos(items)
        conceptos = _extraer_conceptos(items)
        for c in conceptos:
            c["pagina"] = n
        montos_all.extend({"pagina": n, "monto": m} for m in montos)
        conceptos_all.extend(conceptos)
        por_pagina.append({
            "pagina": n,
            "n_cifras": len(montos),
            "suma_cifras": float(sum(montos)),
        })
        print(f"  pag {n}: {len(items)} textos | {len(montos)} cifras | "
              f"{len(conceptos)} conceptos legibles", flush=True)
    doc.close()

    df_montos = pd.DataFrame(montos_all)
    df_pag = pd.DataFrame(por_pagina)
    df_conc = pd.DataFrame(conceptos_all)

    total = float(df_montos["monto"].sum()) if not df_montos.empty else 0.0

    # --- Salidas para el dashboard (Tab 1) ---
    # Gráfico 1: suma de cifras por página + su % del total digitalizado.
    if not df_pag.empty:
        df_pag["pct_del_total"] = (df_pag["suma_cifras"] / total * 100).round(2) \
            if total else 0.0
    df_pag.to_parquet(PROCESSED / "ocr_1964_por_pagina.parquet", index=False)

    # Gráfico 2 / listado: las 20 mayores cifras + su % del total.
    if not df_montos.empty:
        top_montos = df_montos.sort_values("monto", ascending=False).head(20).copy()
        top_montos["pct_del_total"] = (top_montos["monto"] / total * 100).round(2) \
            if total else 0.0
    else:
        top_montos = pd.DataFrame(columns=["pagina", "monto", "pct_del_total"])
    top_montos.to_parquet(PROCESSED / "ocr_1964_top_montos.parquet", index=False)

    # Extra: conceptos legibles emparejados con su monto (best-effort).
    if not df_conc.empty:
        df_conc = (df_conc.sort_values("monto", ascending=False)
                          .drop_duplicates("concepto").head(15))
    else:
        df_conc = pd.DataFrame(columns=["concepto", "monto", "pagina"])
    df_conc.to_parquet(PROCESSED / "ocr_1964_top_conceptos.parquet", index=False)

    resumen = {
        "paginas_procesadas": fin - inicio + 1,
        "rango_paginas": f"{inicio}-{fin}",
        "cifras_extraidas": int(len(df_montos)),
        "suma_total_cifras": total,
        "cifra_maxima": float(df_montos["monto"].max()) if not df_montos.empty else 0.0,
        "cifra_promedio": float(df_montos["monto"].mean()) if not df_montos.empty else 0.0,
        "cifra_mediana": float(df_montos["monto"].median()) if not df_montos.empty else 0.0,
        "conceptos_legibles": int(len(df_conc)),
    }
    (PROCESSED / "ocr_1964_resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    return resumen


if __name__ == "__main__":
    paginas = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    inicio = int(sys.argv[2]) if len(sys.argv) > 2 else PAGINA_INICIO_DEFECTO
    print(f"[ocr] procesando {paginas} páginas desde la {inicio} ...")
    print(json.dumps(procesar(paginas=paginas, inicio=inicio), ensure_ascii=False, indent=2))
