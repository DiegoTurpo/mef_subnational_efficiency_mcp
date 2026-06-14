"""Motor analítico: métricas exactas del HW y derivación de columnas.

Las fórmulas base son funciones puras. ``agregar_metricas`` aplica esas
fórmulas sobre un DataFrame ya agregado (con columnas ``pim`` y ``devengado``),
manteniendo la lógica analítica separada del IO (que vive en data_pipeline.py).
"""
from __future__ import annotations

import pandas as pd


def avance(devengado: float, pim: float) -> float:
    """Avance % de ejecución = (Devengado / PIM) * 100.

    Devuelve 0.0 cuando el PIM es 0 para evitar división por cero.
    """
    return (devengado / pim * 100.0) if pim else 0.0


def saldo_no_devengado(pim: float, devengado: float) -> float:
    """Saldo no devengado = PIM - Devengado."""
    return pim - devengado


def agregar_metricas(df: pd.DataFrame) -> pd.DataFrame:
    """Añade ``saldo_no_devengado`` y ``avance_pct`` a un DataFrame que ya
    contiene ``pim`` y ``devengado`` agregados.
    """
    out = df.copy()
    out["saldo_no_devengado"] = out["pim"] - out["devengado"]
    out["avance_pct"] = (out["devengado"] / out["pim"] * 100.0).where(out["pim"] > 0, 0.0)
    out["avance_pct"] = out["avance_pct"].round(2)
    return out
