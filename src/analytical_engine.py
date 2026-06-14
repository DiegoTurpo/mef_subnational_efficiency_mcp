"""Motor analítico: métricas exactas del HW y agregaciones presupuestales.

Las fórmulas base (puras) se definen aquí. Las agregaciones por departamento /
unidad ejecutora se añaden en el branch feature/data-snapshot-pipeline.
"""
from __future__ import annotations


def avance(devengado: float, pim: float) -> float:
    """Avance % de ejecución = (Devengado / PIM) * 100.

    Devuelve 0.0 cuando el PIM es 0 para evitar división por cero.
    """
    return (devengado / pim * 100.0) if pim else 0.0


def saldo_no_devengado(pim: float, devengado: float) -> float:
    """Saldo no devengado = PIM - Devengado."""
    return pim - devengado
