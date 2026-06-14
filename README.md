# mef_subnational_efficiency_mcp

Sistema **multi-agente local** para auditar el gasto público del Perú usando
Claude Code Skills, un **servidor MCP local** y **PaddleOCR**: analiza la
ejecución presupuestal **2025** del MEF y digitaliza registros históricos de
**1964**.

> Tarea HW_05 — Auditoría del Gasto Público vía Sistemas Multi-Agente, Claude
> Code Skills y MCP Local.

---

## Arquitectura

| Capa | Tecnología | Rol |
|------|------------|-----|
| Servidor MCP | `FastMCP` (SDK oficial) + `httpx` | 10 herramientas sobre la API CKAN del portal |
| Ingesta / datos | `DuckDB` + `pandas` → `Parquet` | Procesa sin saturar memoria (anti-flooding) |
| OCR histórico | `PaddleOCR` + `PyMuPDF` | Digitaliza 15+ páginas de 1964 |
| Dashboard | `Streamlit` + `Plotly` | 4 pestañas (2025 + 1964) |
| Agentes | 2 Claude Code Skills | Executor (construye) + Evaluator (audita/pule) |

## Fuentes de datos

- **2025:** dataset *“Presupuesto y Ejecución de Gasto – Devengado Mensual”* del
  portal `datosabiertos.gob.pe` (CSV `2025-Gasto-Devengado-Mensual.csv`, con
  `MONTO_PIM`, `MONTO_DEVENGADO_ANUAL`, departamento, pliego, etc.).
- **1964:** PDF de la *Cuenta General de la República (1964)* →
  `data/raw_pdfs/cuenta_general_1964.pdf` (descarga manual).
- **Geo:** `peru_departamental_simple.geojson` (repo `juaneladio/peru-geojson`).

## Métricas

- **Avance de ejecución** = `(Devengado / PIM) × 100`
- **Saldo No Devengado** = `PIM − Devengado`

---

## Estructura del proyecto

```
mef_subnational_efficiency_mcp/
├── app.py                    # Dashboard Streamlit (4 tabs)
├── requirements.txt
├── .streamlit/config.toml
├── .claude/skills/           # Skills Executor y Evaluator (.json + SKILL.md)
├── src/
│   ├── mcp_server.py         # Servidor MCP + 10 herramientas
│   ├── data_pipeline.py      # Ingesta 2025 (DuckDB → Parquet)
│   ├── ocr_engine.py         # OCR de 1964 (PaddleOCR + PyMuPDF)
│   ├── analytical_engine.py  # Métricas (Avance, Saldo No Devengado)
│   └── utils.py              # Cliente CKAN + helpers
├── data/
│   ├── raw_pdfs/             # PDF crudo de 1964 (no versionado)
│   ├── snapshots/            # Muestras de esquema (5–10 filas)
│   └── processed/            # Salidas Parquet "microscópicas"
└── video/link.txt            # Enlace del video de presentación
```

---

## Requisitos e instalación

> ⚠️ Usar **Python 3.12** (PaddleOCR no soporta 3.14).

```powershell
# Crear entorno virtual con Python 3.12
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Instalar dependencias
pip install -r requirements.txt
```

## Uso

```powershell
# 1) Servidor MCP (transporte stdio, sin auth)
py -3.12 src/mcp_server.py

# 2) Dashboard
py -3.12 -m streamlit run app.py
```

---

## Flujo de desarrollo (Git)

El proyecto se construye por componentes en branches `feature/*` y se integra a
`main` mediante Pull Requests (nunca commits directos a `main`):

`feature/mcp-server-core` · `feature/data-snapshot-pipeline` ·
`feature/historical-1964-paddle-ocr` · `feature/executor-dashboard-draft` ·
`feature/evaluator-qa-refinement`

---

## Notas de ejecución

- Los **Parquet procesados** (`data/processed/`) ya están versionados, así que el
  dashboard funciona tras clonar sin reprocesar los GB de origen.
- El **CSV crudo del MEF** (~2.66 GB) se descarga a una carpeta temporal del
  sistema (fuera del repo) cuando se ejecuta el pipeline.
- **PaddleOCR/CPU**: el código fija `FLAGS_use_mkldnn=0` automáticamente para
  evitar un fallo de oneDNN en PaddlePaddle 3.x (no requiere acción manual).
- El **reporte de auditoría** del Evaluator está en `docs/evaluator_report.md` y
  se muestra en el Tab 4 del dashboard.
