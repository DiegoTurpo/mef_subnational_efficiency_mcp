---
name: executor-skill
description: Ejecutor de ingeniería de datos del proyecto MEF. Úsalo para actualizar/procesar el gasto público de un periodo (ej. "run executor_skill for period 2025-12"), disparar el OCR de 1964 o regenerar los datos del dashboard. Extrae vía el MCP local, procesa con DuckDB/PaddleOCR y deja los Parquet listos en data/processed/.
---

# Executor Skill — Ingeniería de Datos

Eres el **agente ejecutor** del proyecto `mef_subnational_efficiency_mcp`. Tu
trabajo es **producir**: extraer datos del MEF, procesarlos y dejar listos los
insumos del dashboard, **sin volcar datos crudos al contexto** (Regla 1).

## Cuándo actuar
- "run executor_skill for period `AAAA`" o "`AAAA-MM`" (ej. `2025` o `2025-12`).
- "execute mef_update for `AAAA-Qn`".
- Cuando haya que (re)generar los datos del dashboard o procesar el OCR de 1964.

## Flujo de trabajo

1. **Inspección (anti-flooding).** Usa el MCP para localizar el dataset y mirar
   solo el esquema:
   - `buscar_datasets("devengado-mensual")` → obtén el slug.
   - `obtener_detalle_dataset(slug)` → URL del CSV del año.
   - `inspeccionar_esquema_csv(url)` → confirma columnas (MONTO_PIM,
     MONTO_DEVENGADO_ANUAL, DEPARTAMENTO_EJECUTORA_NOMBRE, ...). **No** descargues
     el CSV completo al contexto.

2. **Pipeline 2025.** Ejecuta el procesamiento local del periodo (descarga +
   DuckDB → Parquet):
   ```bash
   py -3.12 src/data_pipeline.py <PERIODO>     # ej. 2025  o  2025-12
   ```
   Genera en `data/processed/`: `kpis_<año>`, `departamentos_<año>`,
   `sectores_<año>`, `unidades_ejecutoras_<año>`, `devengado_mensual_<año>` (.parquet).

3. **OCR histórico 1964** (si aplica):
   ```bash
   py -3.12 src/ocr_engine.py 15 664           # 15 páginas con matrices densas
   ```
   Genera `ocr_1964_*.parquet` y `ocr_1964_resumen.json`.

4. **Dashboard.** Asegura que `app.py` lee solo `data/processed/` y levanta:
   ```bash
   py -3.12 -m streamlit run app.py
   ```

## Métricas (exactas)
- Avance de ejecución = `Devengado / PIM * 100`
- Saldo No Devengado = `PIM - Devengado`

## Reglas
- Nunca ingieras CSV/JSON crudos completos: usa esquema + muestras + agregados.
- 1964 y 2025 son resúmenes **independientes** (sin comparación cross-época).
- Deja salidas pequeñas (Parquet) que Streamlit pueda leer rápido.

> Tras producir los datos, el **evaluator-skill** audita, optimiza (`@st.cache_data`),
> aplica estilos y documenta los hallazgos.
