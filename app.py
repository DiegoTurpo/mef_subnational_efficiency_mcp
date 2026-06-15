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

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data" / "processed"
GEO = ROOT / "data" / "geo" / "peru_departamentos.geojson"
ANIO = 2025

st.set_page_config(page_title="MEF · Auditoría de Eficiencia Subnacional",
                   layout="wide", page_icon="🇵🇪")

# --- Estilos (inyectados por el Evaluator) ---
st.markdown("""
<style>
:root { --rojo: #C8102E; --tinta: #1a1a1a; }
.block-container { padding-top: 2.2rem; max-width: 1300px; }
h1 { font-weight: 800; letter-spacing: -0.5px; }
h2, h3 { color: var(--tinta); }
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #ececec;
    border-left: 5px solid var(--rojo);
    border-radius: 10px;
    padding: 14px 18px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
[data-testid="stMetricValue"] { color: var(--rojo); font-weight: 700; }
[data-testid="stMetricLabel"] { opacity: 0.75; }
.stTabs [data-baseweb="tab-list"] { gap: 6px; }
.stTabs [data-baseweb="tab"] { font-weight: 600; padding: 8px 14px; }
</style>
""", unsafe_allow_html=True)


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


@st.cache_data
def cargar_vulnerabilidad() -> pd.DataFrame:
    """Hogares del programa JUNTOS por departamento (proxy de vulnerabilidad)."""
    return cargar_parquet("vulnerabilidad_juntos.parquet")


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
        h1, h2, h3, h4 = st.columns(4)
        h1.metric("Páginas digitalizadas (OCR)", resumen.get("paginas_procesadas", 0))
        h2.metric("Cifras financieras extraídas", f"{resumen.get('cifras_extraidas', 0):,}")
        h3.metric("Mayor cifra detectada", soles(resumen.get("cifra_maxima", 0)))
        h4.metric("Cifra mediana", soles(resumen.get("cifra_mediana", 0)))
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

    if not top_montos.empty and "pct_del_total" in top_montos.columns:
        with st.expander("📋 Ranking de mayores cifras digitalizadas (% del total)"):
            rk = top_montos.head(15).rename(columns={
                "pagina": "Página", "monto": "Monto (S/)",
                "pct_del_total": "% del total",
            })
            st.dataframe(
                rk, hide_index=True, width="stretch",
                column_config={
                    "Monto (S/)": st.column_config.NumberColumn(format="S/ %.2f"),
                    "% del total": st.column_config.NumberColumn(format="%.2f%%"),
                },
            )

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

        st.markdown("#### Estancamiento del gasto vs. vulnerabilidad social")
        vuln = cargar_vulnerabilidad()
        dv = d.merge(vuln, on="departamento", how="inner")
        if not dv.empty:
            r = float(np.corrcoef(dv["hogares_juntos"], dv["avance_pct"])[0, 1])
            col_g, col_r = st.columns([3, 1])
            fig2 = px.scatter(
                dv, x="hogares_juntos", y="avance_pct", size="pim",
                color="avance_pct", color_continuous_scale="RdYlGn",
                range_color=(75, 100), hover_name="departamento",
                labels={"hogares_juntos": "Hogares en JUNTOS (vulnerabilidad)",
                        "avance_pct": "Avance de ejecución 2025 (%)"},
            )
            m, b = np.polyfit(dv["hogares_juntos"], dv["avance_pct"], 1)
            xs = np.array([dv["hogares_juntos"].min(), dv["hogares_juntos"].max()])
            fig2.add_scatter(x=xs, y=m * xs + b, mode="lines", name="Tendencia",
                             line=dict(color="#444", dash="dash"))
            fig2.update_layout(height=460)
            col_g.plotly_chart(fig2, width="stretch")
            col_r.metric("Correlación (Pearson)", f"{r:+.2f}")
            if r <= -0.3:
                interp = ("inversa: los departamentos más vulnerables ejecutan "
                          "**menos** su presupuesto (doble penalidad).")
            elif r >= 0.3:
                interp = ("directa: los más vulnerables ejecutan **más** su "
                          "presupuesto.")
            else:
                interp = ("débil: no hay una relación lineal clara entre "
                          "vulnerabilidad y avance de ejecución.")
            col_r.caption(f"Avance de ejecución 2025 vs. hogares en pobreza "
                          f"(JUNTOS). Correlación {interp}")
            st.caption("Fuente de vulnerabilidad: Programa JUNTOS 2025 — hogares "
                       "afiliados por ubigeo (datosabiertos.gob.pe).")
        else:
            st.info("No se pudo cruzar con los datos de vulnerabilidad (JUNTOS).")
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
    # Interfaz de cambio de periodo (period-driven): los periodos disponibles se
    # detectan por los Parquet de KPIs presentes en data/processed/.
    periodos = sorted(p.stem.replace("kpis_", "")
                      for p in PROCESSED.glob("kpis_*.parquet"))
    st.selectbox(
        "Periodo analizado", periodos or [str(ANIO)],
        help="Genera nuevos periodos con: run executor_skill for period AAAA-MM",
    )

    st.divider()
    st.markdown("### 📋 Reporte de Auditoría del Evaluator")
    reporte = ROOT / "docs" / "evaluator_report.md"
    if reporte.exists():
        st.markdown(reporte.read_text(encoding="utf-8"))
    else:
        st.info("Aún no se ha generado el reporte de auditoría.")
