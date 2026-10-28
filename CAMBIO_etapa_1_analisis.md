# CAMBIO · Etapa 1 · el análisis de la pipeline (28-oct-2026)

Etapa 1 del plan de etapas (`PLAN_etapas.md`). Antes de hacer números de negocio, describir la materia prima.

## Misión

Describir la pipeline, pasada y futura, antes de predecirla: cuánto dinero hay, si crece frente al año anterior, su ritmo a lo largo del año, la proporción de licencias de 1, 2 y 3 años, la adquisición y su tendencia, si la composición está cambiando, la tasa de renovación y la revalorización tal cual fueron, las subidas de precio que ha habido, los estados del cliente y lo pronto que aparecen los softcancel. Todo es descriptivo y sale solo de la pipeline: tablas, resúmenes numéricos y gráficos de la evolución en el tiempo, y una recta de regresión sobre lo que debería ser razonablemente estable, para decir si es estable, sube o baja.

## Las tres palabras

| | Qué es |
|---|---|
| **Cerrado** | un mes anterior al mes en curso: venció y su resultado (lo renovado) se conoce |
| **Futuro** | el mes en curso y los que siguen: su pipeline se conoce, su resultado no |
| **Completo** | un mes futuro cuyas licencias de 1 año ya se vendieron o renovaron (su mes de origen, 12 meses antes, está cerrado): hasta el mes en curso + 11. Los posteriores aún se llenan y no se comparan con el año anterior |

## Qué hace (`stage_1_analysis.py`)

Sobre el dataset de la etapa 0 (construido en la misma ejecución, o el guardado):

| Sección | Tabla (`sff_e1_*`) | Qué cuenta |
|---|---|---|
| La pipeline por mes | `e1_pipeline_mes` | unidades y USD que vencen, renovado, tasa en unidades y en USD, uplift (base exacta), y el mismo mes del año anterior |
| La pipeline por año | `e1_pipeline_anio` | el dinero de cada año y el **crecimiento sobre meses comparables**: los meses cerrados o completos frente a los mismos meses del año anterior |
| Mes contra mes | `e1_mes_contra_mes` | el último mes cerrado frente al mismo mes del año anterior (y los últimos 12 cerrados frente a los 12 anteriores), por dimensión y valor: dónde están las diferencias |
| El plazo | `e1_plazo_mes` | la parte de 1, 2 y 3 años cada mes |
| La tasa | `e1_tasa_mes_por` | la tasa real de cada mes cerrado, total y por región, plazo y origen, con su banda binomial |
| La revalorización | `e1_uplift_mes` | el uplift del mes (base exacta), el de las renovaciones aisladas, y cuánto de lo renovado está en el ciclo de una subida |
| Las subidas de precio | `e1_subidas_precio` | las detectadas con **el mismo detector del paso 3.1** (`price_increases.py`), con su ciclo y si sigue abierto hoy |
| La adquisición | `e1_adquisicion_mes` | por mes de venta (vencimiento menos el plazo) y plazo; solo los meses **observables** (sus licencias vencen dentro del extracto); las de 1 año son la serie principal |
| La composición | `e1_composicion_anual`, `e1_composicion_cambio` | la parte del USD por dimensión y valor cada año, frente al año anterior **sobre los mismos meses**; el cambio de composición Σ\|Δ parte\|/2 |
| Los estados | `e1_estados_mes` | la parte de cada estado en lo que vence: final en los meses cerrados, lo visto hasta hoy en los futuros |
| Los estados tempranos | `e1_estados_tempranos` | por cohorte (mes de vencimiento) y estado fechado: la parte ya en el estado en su **primer mes de vida** y en los dos primeros (licencias de 1 año) |
| Los estados al horizonte | `e1_estados_horizonte` | los meses que vienen: lo visible hoy frente a la cohorte de hace un año **al mismo horizonte**, y su final |
| El retail to subscription | `e1_retail_to_subscription` | los ingresos de cada mes cerrado frente al año anterior |
| Las transiciones de plazo | `e1_transiciones_plazo` | por año y plazo de origen, a qué plazo renovaron |
| Las tendencias | `e1_tendencias` | una fila por KPI: media de los últimos 12 meses frente a los 12 anteriores, pendiente anual con su p-valor (sube · baja · estable), estacionalidad (amplitud, meses altos y bajos) |

**Dónde están las diferencias (mes contra mes).** Lo renovado = USD que vence × tasa base × uplift (tasa base: la parte del USD que vence que renovó, a precio de vencimiento). Su cambio se reparte en tres efectos que suman exactamente la diferencia:
- efecto pipeline = Δ vence × tasa antes × uplift antes (venció más o menos);
- efecto tasa = vence hoy × Δ tasa × uplift antes (renovó más o menos);
- efecto uplift = vence hoy × tasa hoy × Δ uplift (renovó a otro precio).

Sin la base exacta del uplift en el extracto, los dos últimos son uno (efecto rendimiento).

**La recta de regresión** (`trend_of`): el valor sobre el tiempo en años; la pendiente con su p-valor (p < `dynamics_significance` = tendencia); sobre el residuo, el efecto del mes del calendario (test F) con los meses altos y bajos más allá de dos errores. Necesita `analysis_trend_min_months` (12) para la recta y `analysis_season_min_months` (24) para la estacionalidad. Una serie constante no tiene tendencia ni estacionalidad por mucho que el p-valor diga.

**Lo que escribe en disco:** `salida/analisis/ANALISIS_pipeline.md` con el resumen «en una página», una sección por tabla y sus gráficos (`01_pipeline_mensual`, `02_ritmo_pipeline`, `02b_mes_contra_mes`, `03_plazo`, `04_tasa`, `05_uplift`, `06_adquisicion`, `07_composicion`, `08_estados`, `09_retail_to_subscription`).

**En pantalla:** las acciones de la etapa, y la VALORACIÓN (las líneas del resumen) al final.

## Cómo se usa

| Comando | Qué ejecuta |
|---|---|
| `python main.py` | etapa 0 + **etapa 1** + forecast dynamics + forecast |
| `python main.py solo_analisis` | solo la etapa 1, sobre el dataset guardado |
| `python main.py sin_analisis` | sin la etapa 1 |
| `python main.py escenario` | `sin_datos` + `sin_analisis` + `sin_aprender` |

En `main.py`: `RUN_STAGE_1_ANALYSIS = True / False`. En un notebook:

```python
from stage_1_analysis import analyse_the_pipeline
analisis = analyse_the_pipeline(raw, configuracion)
analisis["tables"]["tendencias"]
```

Config nuevos (`[E1]`): `analysis_trend_min_months` (12), `analysis_season_min_months` (24), `analysis_top_values` (8: valores de una dimensión dibujados o listados; el resto, «otros»).

## Solapes anotados para la refactorización (H8)

Describen el mismo dato desde el núcleo, después del forecast. Siguen funcionando; cuando se cierren las etapas, se quedan con lo que necesita el núcleo (el forecast junto a lo real) y la descripción queda en la etapa 1:
- `informe_forecast.py`: el capítulo 1 (el dato real, 1.1–1.7), 8.2 (tasa por año), 8.5 (composición), 8.9 (subidas detectadas), 8.10 (transiciones de plazo);
- `block_8_output.py` 8.6: el perfil de la pipeline (`sff_perfil_datos`);
- `block_1_preparation.py`: los informes del raw en pantalla (`log_raw_report`, `report_the_closed_months`).

Cada uno lleva la nota en su cabecera.

## Comprobado

**`test_stage_1_analysis.py`**, 35 comprobaciones:
- la pipeline por mes y por año suma lo del raw; cerrado, futuro y completo donde deben; el crecimiento sobre meses comparables;
- la recta: una serie que sube un 10 % al año es «sube» con esa pendiente; una constante es «estable» sin estacionalidad; una senoidal tiene estacionalidad con abril alto y octubre bajo; pocos meses, sin tendencia; una parte en puntos;
- mes contra mes: los tres efectos suman la diferencia en cada fila, y cada dimensión suma el total;
- los estados fechados: primer mes ≤ dos primeros ≤ final; el horizonte de cada mes futuro;
- el sintético parecido al real: una adquisición de 2 años vendida hace menos de 24 meses no es observable; las de 1 año cuadran con las unidades que vencen 12 meses después; las partes suman 1; el año que viene se compara sobre sus mismos meses; 30 subidas detectadas; los tres plazos; 14 KPIs con tendencia; el markdown y 9 gráficos;
- las etapas y las palabras `sin_analisis`, `escenario`, `solo_analisis`.

**Sintético parecido al real** (374.000 filas): 11 s.

## Lo que viene

- Lo que el usuario vea en los datos reales que falte aquí.
- H8: quitar de los otros sitios lo que ya describe esta etapa.
