"""Indicador de vulnerabilidad social por departamento, desde el portal.

Fuente: Programa JUNTOS (transferencias condicionadas a hogares en pobreza),
dataset "Resumen de Hogares afiliados y abonados por ubigeo" de
datosabiertos.gob.pe. Se agregan los hogares afiliados por departamento como
proxy de vulnerabilidad social — todo dentro del portal exigido por el HW.

Uso:  py -3.12 src/vulnerabilidad.py
"""
from __future__ import annotations

import io
import sys
import unicodedata
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import utils

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
SLUG = "resumen-de-hogares-afiliados-y-abonados-por-ubigeo-2024-programa-juntos"

# JUNTOS usa "CALLAO"; el gasto del MEF usa el nombre largo.
_NORM = {"CALLAO": "PROVINCIA CONSTITUCIONAL DEL CALLAO"}


def _sin_acentos(s: str) -> str:
    """Normaliza a mayúsculas sin tildes (JUNTOS trae HUÁNUCO; el gasto, HUANUCO)."""
    s = str(s).strip().upper()
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def _url_xlsx() -> str:
    d = utils.get_dataset(SLUG)
    for r in d.get("resources", []):
        u = r.get("url", "")
        if u.lower().endswith(".xlsx") and "bimestre_I_2024" in u:
            return u
    # fallback: primer xlsx disponible
    for r in d.get("resources", []):
        if r.get("url", "").lower().endswith(".xlsx"):
            return r["url"]
    raise RuntimeError("No se encontró el xlsx de JUNTOS en el portal.")


def generar() -> dict:
    """Descarga JUNTOS, agrega hogares afiliados por departamento y guarda Parquet."""
    PROCESSED.mkdir(parents=True, exist_ok=True)
    with utils._client() as c:
        r = c.get(_url_xlsx())
        r.raise_for_status()
        data = r.content
    df = pd.read_excel(io.BytesIO(data))
    df["DEPARTAMENTO"] = df["DEPARTAMENTO"].map(_sin_acentos).replace(_NORM)
    agg = (df.groupby("DEPARTAMENTO", as_index=False)["AFILIADOS"].sum()
             .rename(columns={"DEPARTAMENTO": "departamento",
                              "AFILIADOS": "hogares_juntos"})
             .sort_values("hogares_juntos", ascending=False))
    agg.to_parquet(PROCESSED / "vulnerabilidad_juntos.parquet", index=False)
    return {"departamentos": int(len(agg)),
            "total_hogares_juntos": int(agg["hogares_juntos"].sum())}


if __name__ == "__main__":
    print(generar())
