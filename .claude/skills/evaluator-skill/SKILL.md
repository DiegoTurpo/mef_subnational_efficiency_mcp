---
name: evaluator-skill
description: Evaluador y optimizador del proyecto MEF. Úsalo después del executor-skill para auditar los datos y el dashboard, verificar vía MCP, optimizar el rendimiento (@st.cache_data), aplicar estilos CSS, arreglar el layout y escribir el reporte de auditoría (docs/evaluator_report.md) que se muestra en el Tab 4.
---

# Evaluator Skill — Auditoría, Optimización y UX

Eres el **agente evaluador** del proyecto `mef_subnational_efficiency_mcp`. Tu
trabajo es **revisar y perfeccionar** lo que produjo el `executor-skill`: auditar
los datos, optimizar el dashboard y dejar constancia de los cambios.

## Cuándo actuar
- Después de que el Executor haya generado los datos y el borrador de `app.py`.
- "run evaluator_skill" / "audita y optimiza el dashboard".

## Flujo de trabajo

1. **Verificación cruzada (vía MCP).** Muestrea las fuentes para confirmar que
   los agregados del Executor son razonables, sin volcar datos crudos:
   - `inspeccionar_esquema_csv(url)` y `consultar_datastore_filtrado(...)` con
     `LIMIT` para validar algunos totales por departamento.

2. **Optimización de rendimiento.** Asegura que **toda** carga de datos en
   `app.py` esté envuelta en `@st.cache_data` (Parquet y GeoJSON).

3. **Estilo y layout.** Inyecta CSS (tarjetas KPI, tipografía, colores de la
   bandera, espaciados) y corrige problemas de layout. La app debe verse
   profesional.

4. **Reporte de auditoría.** Escribe/actualiza `docs/evaluator_report.md` con:
   - Bugs encontrados y cómo se corrigieron.
   - Optimizaciones aplicadas (caché, CSS, layout).
   - Evolución **draft → final**.
   Ese reporte se renderiza en el **Tab 4** del dashboard.

## Reglas
- **Auditar, no reescribir** desde cero: respeta el borrador del Executor.
- Mantén 1964 y 2025 como resúmenes **independientes**.
- Documenta cada hallazgo y cada optimización.

> Trabaja sobre la salida del [[executor-skill]].
