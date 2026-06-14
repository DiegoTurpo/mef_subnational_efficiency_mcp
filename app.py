"""Dashboard Streamlit (4 pestañas) — punto de entrada de la app.

El borrador funcional se construye en el branch feature/executor-dashboard-draft
y se pule (caché, CSS, reporte de auditoría) en feature/evaluator-qa-refinement.

Ejecutar:  py -3.12 -m streamlit run app.py
"""
import streamlit as st

st.set_page_config(
    page_title="MEF · Auditoría de Eficiencia Subnacional",
    layout="wide",
)

st.title("MEF · Auditoría de Eficiencia Subnacional")
st.caption("Gasto público 2025 (MEF) + digitalización histórica 1964 vía OCR")

st.info(
    "🚧 Dashboard en construcción. Las 4 pestañas se implementan en los "
    "branches del **Executor** (draft) y el **Evaluator** (refinamiento)."
)
