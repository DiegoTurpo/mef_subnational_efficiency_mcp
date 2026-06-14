"""Dashboard Streamlit — Auditoría de Eficiencia Subnacional del Gasto Público.

4 pestañas:
  1. Resumen ejecutivo dual (KPIs 2025 + digitalización histórica 1964)
  2. Distribución territorial 2025 (mapa por departamento)
  3. "Hall of Shame" 2025 (unidades ejecutoras con peor avance, PIM > 10M)
  4. Bitácora multi-agente (Executor + Evaluator)

Lee SOLO los Parquet reducidos de data/processed/ (Regla 1 anti-flooding).
Borrador construido por el Executor; el Evaluator añade caché/CSS/auditoría.

Ejecutar:  py -3.12 -m streamlit run app.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data" / "processed"
GEO = ROOT / "data" / "geo" / "peru_departamentos.geojson"
ANIO = 2025

st.set_page_config(page_title="MEF · Auditoría de Eficiencia Subnacional",
                   layout="wide", page_icon="🇵🇪")


# --------------------------------------------------------------------------
#  Carga de datos (cacheada — lee solo salidas pequeñas)
# --------------------------------------------------------------------------
@st.cache_data
def cargar_parquet(nombre: str) -> pd.DataFrame:
    ruta = PROCESSED / nombre
    return pd.read_parquet(ruta) if ruta.exists() else pd.DataFrame()


@st.cache_data
def cargar_json(nombre: str) -> dict:
    ruta = PROCESSED / nombre
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}


@st.cache_data
def cargar_geojson() -> dict:
    return json.loads(GEO.read_text(encoding="utf-8")) if GEO.exists() else {}


def soles(x: float) -> str:
    """Formatea un monto en soles con escala legible."""
    x = float(x or 0)
    if abs(x) >= 1e9:
        return f"S/ {x/1e9:,.2f} mil M"
    if abs(x) >= 1e6:
        return f"S/ {x/1e6:,.1f} M"
    return f"S/ {x:,.0f}"


# --------------------------------------------------------------------------
#  Encabezado
# --------------------------------------------------------------------------
st.title("🇵🇪 MEF · Auditoría de Eficiencia Subnacional")
st.caption(f"Gasto público {ANIO} (MEF · datosabiertos.gob.pe) + "
           "digitalización histórica 1964 vía PaddleOCR")

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Resumen Ejecutivo",
    "🗺️ Distribución Territorial",
    "🚨 Hall of Shame",
    "🤖 Bitácora Multi-Agente",
])


# ==========================================================================
#  TAB 1 — Resumen ejecutivo dual (2025 + 1964, independientes)
# ==========================================================================
with tab1:
    kpis = cargar_parquet(f"kpis_{ANIO}.parquet")
    st.subheader(f"Ejecución Presupuestal Nacional {ANIO}")
    if not kpis.empty:
        k = kpis.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("PIM Total", soles(k["pim"]))
        c2.metric("Devengado", soles(k["devengado"]))
        c3.metric("Avance Nacional", f"{k['avance_pct']:.2f}%")
        c4.metric("Saldo No Devengado", soles(k["saldo_no_devengado"]))
        st.info(
            f"En {ANIO}, el Estado peruano ejecutó el **{k['avance_pct']:.1f}%** de su "
            f"presupuesto modificado (PIM). Quedaron **{soles(k['saldo_no_devengado'])}** "
            "sin devengar — el principal cuello de botella de la gestión fiscal: "
            "recursos asignados que no llegaron a ejecutarse."
        )

        serie = cargar_parquet(f"devengado_mensual_{ANIO}.parquet")
        if not serie.empty:
            fig = px.bar(serie, x="mes", y="devengado",
                         title=f"Devengado mensual {ANIO} (S/)",
                         labels={"mes": "Mes", "devengado": "Devengado (S/)"})
            fig.update_traces(marker_color="#C8102E")
            st.plotly_chart(fig, width="stretch")
    else:
        st.warning("No hay KPIs procesados. Ejecuta: `py -3.12 src/data_pipeline.py 2025`")

    st.divider()

    # --- Sección histórica 1964 (independiente, sin comparar con 2025) ---
    st.subheader("📜 Digitalización Histórica — Cuenta General de la República 1964")
    resumen = cargar_json("ocr_1964_resumen.json")
    if resumen:
        h1, h2, h3 = st.columns(3)
        h1.metric("Páginas digitalizadas (OCR)", resumen.get("paginas_procesadas", 0))
        h2.metric("Cifras financieras extraídas", f"{resumen.get('cifras_extraidas', 0):,}")
        h3.metric("Mayor cifra detectada", soles(resumen.get("cifra_maxima", 0)))
        st.caption(
            f"Procesadas con PaddleOCR las páginas {resumen.get('rango_paginas', '')} "
            "del balance de 1964. La extracción se centra en las **cifras** "
            "(robustas); el reconocimiento de nombres es limitado por la calidad "
            "del escaneo de 1964."
        )

    cg1, cg2 = st.columns(2)
    por_pag = cargar_parquet("ocr_1964_por_pagina.parquet")
    if not por_pag.empty:
        fig = px.bar(por_pag, x="pagina", y="suma_cifras",
                     title="Cifras digitalizadas por página (1964)",
                     labels={"pagina": "Página", "suma_cifras": "Suma de cifras"})
        fig.update_traces(marker_color="#1f4e79")
        cg1.plotly_chart(fig, width="stretch")

    top_montos = cargar_parquet("ocr_1964_top_montos.parquet")
    if not top_montos.empty:
        tm = top_montos.head(15).copy()
        tm["etiqueta"] = "pág " + tm["pagina"].astype(str)
        fig = px.bar(tm.sort_values("monto"), x="monto", y="etiqueta",
                     orientation="h", title="Mayores cifras extraídas de 1964",
                     labels={"monto": "Monto", "etiqueta": "Origen"})
        fig.update_traces(marker_color="#c9a227")
        cg2.plotly_chart(fig, width="stretch")

    st.caption("ℹ️ Las épocas 1964 y 2025 se presentan como resúmenes "
               "independientes (sin comparación cross-época).")


# ==========================================================================
#  TAB 2 — Distribución territorial 2025
# ==========================================================================
with tab2:
    st.subheader(f"Distribución Territorial del Gasto {ANIO}")
    dep = cargar_parquet(f"departamentos_{ANIO}.parquet")
    geo = cargar_geojson()

    if not dep.empty and geo:
        d = dep.copy()
        # El GeoJSON usa "CALLAO"; nuestros datos "PROVINCIA CONSTITUCIONAL DEL CALLAO".
        d["dep_geo"] = d["departamento"].replace(
            {"PROVINCIA CONSTITUCIONAL DEL CALLAO": "CALLAO"})

        fig = px.choropleth(
            d, geojson=geo, featureidkey="properties.NOMBDEP",
            locations="dep_geo", color="avance_pct",
            color_continuous_scale="RdYlGn", range_color=(75, 100),
            hover_name="departamento",
            hover_data={"dep_geo": False, "avance_pct": ":.1f"},
            labels={"avance_pct": "Avance %"},
            title=f"Avance de ejecución por departamento ({ANIO})",
        )
        fig.update_geos(fitbounds="locations", visible=False)
        fig.update_layout(height=600, margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig, width="stretch")

        st.markdown("#### Estancamiento presupuestal por departamento")
        st.caption("Saldo No Devengado = recursos asignados que no se ejecutaron "
                   "(proxy de estancamiento). Una capa futura puede cruzarlo con "
                   "indicadores de vulnerabilidad social.")
        top_saldo = d.sort_values("saldo_no_devengado", ascending=False).head(12)
        fig2 = px.bar(top_saldo.sort_values("saldo_no_devengado"),
                      x="saldo_no_devengado", y="departamento", orientation="h",
                      labels={"saldo_no_devengado": "Saldo No Devengado (S/)",
                              "departamento": ""})
        fig2.update_traces(marker_color="#C8102E")
        st.plotly_chart(fig2, width="stretch")
    else:
        st.warning("Faltan datos de departamentos o el GeoJSON.")


# ==========================================================================
#  TAB 3 — Hall of Shame 2025
# ==========================================================================
with tab3:
    st.subheader(f"🚨 Hall of Shame — Unidades Ejecutoras con peor avance ({ANIO})")
    st.caption("Unidades ejecutoras con PIM > S/ 10 millones, ordenadas por menor "
               "avance de ejecución (mayor gasto bloqueado primero).")
    ue = cargar_parquet(f"unidades_ejecutoras_{ANIO}.parquet")
    if not ue.empty:
        c1, c2 = st.columns(2)
        c1.metric("Unidades ejecutoras (PIM > 10M)", f"{len(ue):,}")
        c2.metric("Saldo no devengado (estas UEs)", soles(ue["saldo_no_devengado"].sum()))

        tabla = ue.sort_values("avance_pct").rename(columns={
            "pliego": "Pliego", "unidad_ejecutora": "Unidad Ejecutora",
            "departamento": "Departamento", "pim": "PIM",
            "devengado": "Devengado", "saldo_no_devengado": "Saldo No Devengado",
            "avance_pct": "Avance %",
        })
        st.dataframe(
            tabla, width="stretch", height=560, hide_index=True,
            column_config={
                "PIM": st.column_config.NumberColumn(format="S/ %.0f"),
                "Devengado": st.column_config.NumberColumn(format="S/ %.0f"),
                "Saldo No Devengado": st.column_config.NumberColumn(format="S/ %.0f"),
                "Avance %": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )
    else:
        st.warning("No hay datos de unidades ejecutoras.")


# ==========================================================================
#  TAB 4 — Bitácora multi-agente (se completa en el branch del Evaluator)
# ==========================================================================
with tab4:
    st.subheader("🤖 Bitácora del Sistema Multi-Agente")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🛠️ Executor Skill")
        st.markdown("Extrae datos vía MCP, dispara el OCR de 1964, calcula métricas "
                    "y construye el borrador del dashboard.")
    with col2:
        st.markdown("#### 🔍 Evaluator Skill")
        st.markdown("Audita datos, optimiza con `@st.cache_data`, aplica estilos y "
                    "documenta bugs y mejoras.")
    st.divider()
    st.info("📋 El reporte de auditoría del Evaluator (evolución draft → final) se "
            "añade en el branch `feature/evaluator-qa-refinement`.")
