# 🔍 Reporte de Auditoría — Evaluator Skill

> Auditoría del trabajo del **Executor**: verificación de datos, optimización y
> pulido de la interfaz. Documenta la evolución **draft → final**.

## 1. Verificación cruzada de datos (vía MCP)

- Se muestreó el esquema del CSV 2025 con `inspeccionar_esquema_csv` (Range HTTP):
  confirmadas las columnas `MONTO_PIM`, `MONTO_DEVENGADO_ANUAL` y
  `DEPARTAMENTO_EJECUTORA_NOMBRE` sin descargar el archivo completo.
- KPIs nacionales validados como razonables: **PIM ≈ S/ 272.4 mil M**,
  **Devengado ≈ S/ 253.7 mil M**, **Avance 93.1 %** (año fiscal cerrado).
- 25 departamentos presentes; sin duplicados tras la agregación con DuckDB.

## 2. Bugs encontrados y corregidos

| # | Hallazgo | Corrección |
|---|----------|------------|
| 1 | `use_container_width` quedó **deprecado** (eliminado tras 2025-12-31) | Migrado a `width="stretch"` en todos los gráficos/tablas |
| 2 | El mapa no pintaba **Callao**: el GeoJSON usa `CALLAO` y los datos `PROVINCIA CONSTITUCIONAL DEL CALLAO` | Mapeo de nombres antes del *join* del coroplético |
| 3 | DuckDB rechazaba el CSV en **latin-1** del MEF | Conversión a UTF-8 al descargar (latin-1 es de 1 byte: seguro por chunks) |
| 4 | La descarga de **2.66 GB** se estancaba en una sola conexión | Descarga **reanudable** con HTTP Range + reintentos |
| 5 | PaddlePaddle 3.x abortaba la inferencia (**oneDNN** `NotImplementedError`) en CPU | `FLAGS_use_mkldnn=0` antes de importar paddle |
| 6 | El primer bloque OCR (pág. 57–71) tenía páginas casi vacías | Selección del bloque **664–678** por densidad de cifras |

## 3. Optimizaciones aplicadas

- **Caché**: todas las cargas de datos (`Parquet` y `GeoJSON`) usan
  `@st.cache_data` → la app recarga al instante.
- **Anti-flooding (Regla 1)**: el dashboard lee **solo** los Parquet reducidos de
  `data/processed/` (KB), nunca los datasets crudos (GB).
- **OCR centrado en cifras**: ante la baja calidad del escaneo de 1964 para
  nombres, el análisis se apoya en las **950 cifras** extraídas (robustas) y su
  distribución por página.
- **UI**: estilos CSS (tarjetas KPI, tipografía, colores de la bandera) y layout
  en columnas; épocas 1964 y 2025 separadas visualmente.

## 4. Evolución draft → final

| Aspecto | Draft (Executor) | Final (Evaluator) |
|---------|------------------|-------------------|
| Estética | Colores por defecto, sin estilos | CSS: tarjetas KPI, tipografía, acentos |
| Tab 4 | Placeholder | Este reporte de auditoría + selector de periodo |
| Caché | Básica | Verificada en todas las cargas |
| Datos | Generados | Verificados de forma cruzada vía MCP |

## 5. Mejoras incorporadas (ronda de refinamiento)

- **Descriptivos 1964**: se añadieron **porcentajes** (cada cifra sobre el total),
  media/mediana y un ranking de mayores cifras en el Tab 1.
- **Vulnerabilidad social (Tab 2)**: se cruzó el avance de ejecución con los
  **hogares del programa JUNTOS 2025** por departamento (proxy de pobreza, dataset
  del propio portal `datosabiertos.gob.pe`, 25/25 departamentos) y se calcula la
  correlación de Pearson. Hallazgo: relación **débil** (r ≈ +0.12) — la ejecución
  del gasto no se explica linealmente por la vulnerabilidad.

## 6. Limitaciones y mejoras futuras

- **OCR de nombres 1964**: limitado por la calidad del escaneo; mejorable con
  modelos OCR específicos para documentos históricos.
- **Más periodos**: el pipeline ya admite periodo dinámico (ej. `2025-12`); falta
  poblar otros años en el dashboard.
