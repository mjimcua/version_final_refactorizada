# PLAN · SFF separado por etapas (28-oct-2026)

**Estado: plan acordado, para ejecutar en los próximos días.** El resultado de este mes se saca con el framework actual. La reestructuración empieza después, pieza a pieza.

**Avance:**

| Fecha | Hito | Qué | Documento |
|---|---|---|---|
| 28-oct-2026 | H2 | etapa 0 · datos (`stage_0_data.py`) y `main` por etapas (`stages.py`: `RUN_STAGE_0_DATA`, `RUN_FORECAST`, `RUN_REPORT`, o `sin_datos`, `solo_datos`, `informe` en la línea de comandos) | `CAMBIO_etapa_0_datos.md` |
| 28-oct-2026 | H3 | etapa 2 · primera forecast dynamic: la maduración de los estados del cliente (`forecast_dynamics.py`; `RUN_STAGE_2_LEARNING`, o `sin_aprender` y `escenario` en la línea de comandos) | `CAMBIO_forecast_dynamics_maduracion.md` |
| 28-oct-2026 | H5 | registro de ejecuciones y referencia congelada (`runs.py`: `sff_ejecuciones`, `sff_ejecucion_foto`, `sff_ejecucion_referencias`; `RUN_KIND`, `RUN_NOTE`, o `escenario` y `referencia` en la línea de comandos) | `CAMBIO_registro_ejecuciones.md` |
| 28-oct-2026 | H7 (primera pieza) | seguimiento: la realidad frente a la referencia entregada, partida en pipeline y rendimiento (informe 9.2) | `CAMBIO_informe_forecast.md` §9.2 |
| 28-oct-2026 | — | renombrado: los «supuestos aprendidos» de la etapa 2 pasan a llamarse **forecast dynamics** (`assumptions.py` → `forecast_dynamics.py`, `sff_s2_*` → `sff_fd_*`) | `CAMBIO_forecast_dynamics_maduracion.md` |
| 28-oct-2026 | — | etapa 0 simplificada tras la revisión de su misión: sin comparación de historia, sin ficha, sin ida y vuelta | `CAMBIO_etapa_0_datos.md` |
| 28-oct-2026 | E1 | etapa 1 · el análisis de la pipeline (`stage_1_analysis.py`; `RUN_STAGE_1_ANALYSIS`, o `sin_analisis` y `solo_analisis` en la línea de comandos): tablas `sff_e1_*`, gráficos y `ANALISIS_pipeline.md`; los solapes con el informe y el perfil de datos, anotados para H8 | `CAMBIO_etapa_1_analisis.md` |
| 28-oct-2026 | H6 | las palancas: `palancas.csv` con lo acordado con negocio, aplicado en el 7.2 (nunca en el examen), con el efecto de cada fila y la ejecución registrada como escenario (`levers.py`) | `CAMBIO_palancas.md` |

## Conclusiones

- **Cada etapa produce algo que se persiste y que la siguiente lee.** Las etapas son el dataset raw validado, el análisis, las forecast dynamics, el núcleo de predicción, la capa de negocio y el seguimiento. Ninguna etapa recalcula lo que hace otra.
- **Una predicción nueva (un corte de datos nuevo) lo recalcula todo.** Dentro de un mismo corte, lo ya calculado se reutiliza: los escenarios del mes solo vuelven a ejecutar el núcleo.
- **El núcleo recibe tres clases de input y ninguna es "lo que el núcleo cree":**
  1. **forecast dynamics**: patrones aprendidos de los datos (aprendemos del pasado, el núcleo los aplica en el presente, el seguimiento confirma con el futuro si se cumplieron);
  2. referencias externas (el forecast de retención, el objetivo de adquisición), en modo *comparar* o *forzar*;
  3. **palancas**: ajustes acordados con los retention managers (una campaña sobre los cancel de una región, por ejemplo), que no son dato real y no tienen por qué serlo.
- **Baseline = el núcleo sin palancas. Escenario = el mismo núcleo con palancas. Referencia = la ejecución entregada a negocio, congelada.** El seguimiento mide la realidad frente a las tres. La pregunta que importa es «¿la campaña acordada ganó a la baseline en su ámbito?».
- **La separación también es de gobierno.** El forecast es un número; cómo se construye es una filosofía, y cómo se cambia es la palanca. Las piezas son independientes, así que cada una se puede compartir o no por separado. Lo que no se entrega es la coordinación: qué dynamics se usan, qué palancas se acuerdan y cómo se lee el seguimiento. Esa coordinación es el trabajo consultivo con los retention managers.

## Las etapas

| # | Etapa | Lee | Produce (persistido) | Sale de lo que hay hoy |
|---|---|---|---|---|
| 0 | **Datos** | SQL de origen | la pipeline del mes en curso, probada (pasos 1.1 y 1.2) y guardada | pasos 1.1–1.4 (dbt opcional para la SQL y los tests) |
| 1 | **Análisis** | raw | la pipeline descrita antes de predecirla (`sff_e1_*`, `ANALISIS_pipeline.md`): cuánto hay y si crece, el ritmo del año, mes contra mes, plazos, tasa, revalorización y subidas, adquisición, composición, estados y estados tempranos, tendencias | hecho (`stage_1_analysis.py`); los solapes del informe (cap. 1, 8.2, 8.5, 8.9, 8.10) y del perfil de datos (8.6) se quitan en H8 |
| 2 | **Aprendizaje** | raw | **forecast dynamics versionadas**, cada una con su corte, la versión de su método y una validación | 4.1 curvas de estados · `term_transitions` · detector de subidas (bloque 3, hoy escrito en 8.4) · niveles del 1.2 · reglas de 5.1 (adquisición) y 6.1 (time series y retail to subscription) |
| 3 | **Núcleo** | raw + forecast dynamics + referencias + palancas | forecast por `run_id`: tasa, revalorización, maduración aplicada, ensamblado, banda; el examen | bloques 2, 3 (estimación), 7 y la aplicación de las cajas de 4, 5 y 6 |
| 4 | **Negocio** | salidas del núcleo | resumen, Power BI, comparación con las referencias, respuestas a preguntas concretas | bloque 8 (8.3–8.4) e informe para negocio |
| 5 | **Seguimiento** | ejecuciones registradas + raw nuevo | realidad frente a referencia, baseline y escenario, por pipeline, resultado y patrones; deriva de las dynamics; resultado de cada palanca | nuevo |

Las cajas del 25-oct (`RateBox`, `StateMaturation`, `FuturePipeline`, `TimeSeriesUniverse`) son las costuras naturales. Lo que está dentro de una caja y se *aprende* pasa a la etapa 2. Lo que se *aplica* se queda en el núcleo.

**Lo que no sale del núcleo:** la predicción de la tasa (escalera, técnica por composición, backtest). Es el núcleo, y sacarla lo vaciaría. La revalorización por celda está en la frontera; se decide al llegar a ella.

## Los inputs del núcleo

### Forecast dynamics (etapa 2)

Un fichero o tabla por dynamic, con un contrato común:

| Campo | Para qué |
|---|---|
| `dinamica`, `version_metodo` | qué es y con qué código se aprendió |
| `corte_datos` | último mes cerrado del raw del que se aprendió |
| `aprendido_a_fecha` | normalmente = corte; en el examen, la fecha de cada origen |
| grano (dims) + valores | p. ej. nivel × grupo × plazo de origen → parte a 1/2/3 años |
| `con_soporte`, `nivel` | de dónde sale el valor de cada grupo |

Dynamics de la primera ola: curvas de maduración de los estados, transiciones de plazo, calendario de subidas, niveles de las dimensiones, reglas de adquisición y de retail to subscription.

### Referencias externas

- El forecast de retención (`forecast_retencion_2027.csv`) y el objetivo de adquisición, cada uno con su modo:
  - `comparar`: se informa la diferencia;
  - `forzar`: el núcleo reparte el total de la referencia con su propia forma, como hace hoy la adquisición con su objetivo.

### Palancas (escenarios)

Un fichero editable (CSV o YAML) con una fila por ajuste acordado:

| Campo | Ejemplo |
|---|---|
| `id`, `descripcion` | `P-2027-01` · campaña de recuperación de cancel en DACH |
| `acordado_con`, `fecha_acuerdo`, `estado` | retention manager DACH · 2026-11-10 · propuesta / acordada / descartada |
| `ambito` (dims) | región = DACH, estado = cancel |
| `periodo` | 2027-03 a 2027-08 |
| `tipo` | `tasa_suma_pp` · `tasa_multiplica` · `uplift_multiplica` · `transicion_fija_parte` · `adquisicion_suma_usd` · `curva_sustituye` |
| `valor` | +3 pp |

Un escenario es un corte, un juego de dynamics, unas referencias con su modo y un conjunto de palancas. El núcleo aplica las palancas después de leer las dynamics y antes de ensamblar. Cada palanca deja una columna de su efecto, para que el resultado se pueda descomponer en baseline más el efecto de cada palanca.

## Registro de ejecuciones

Una tabla `sff_ejecuciones` con una fila por ejecución:
- `run_id`, `corte_datos`, `version_codigo`;
- `tipo`: baseline / escenario / referencia entregada;
- la huella de las dynamics usadas, las palancas y los modos de las referencias;
- fecha y nota.

Las salidas del núcleo se guardan por `run_id`, así que un escenario nunca sobrescribe la baseline. **La referencia entregada se congela:** no se borra y no se recalcula.

## Reglas de diseño

1. **Aprender a fecha X.** La lógica de cada dynamic es una función `aprender(raw, a_fecha)`. La etapa 2 la llama a fecha del corte. El examen del núcleo la llama a fecha de cada origen, para no usar información del futuro. Es el mismo código usado de dos formas.
2. **Las palancas no entran en el examen.** El examen mide el método, no la campaña.
3. **Compatibilidad al arrancar.** El núcleo comprueba que el corte de cada dynamic coincide con el del raw. Fuera de un escenario declarado, la diferencia es un aviso fuerte. También comprueba que la dynamic cubre los grupos, los estados y los plazos del raw.
4. **Recalcular por corte, reutilizar dentro del corte.** Las etapas 0–2 se ejecutan una vez por corte; los escenarios solo ejecutan 3 y 4.
5. **Sin orquestador.** Un script por etapa, un `ejecutar_todo` y el registro de ejecuciones. Todo persistido en SQL Server (esquema por etapa), salvo los ficheros que se editan a mano: palancas y referencias.
6. **Sustitución gradual, con test de igualdad.** El framework actual sigue funcionando. Cada pieza que se extrae tiene un test que compara con lo de antes: mismos números con el mismo corte y sin palancas.
7. **dbt, solo si encaja.** Puede llevar la SQL del raw y sus tests. Por lo que sé, el adaptador de SQL Server no ejecuta modelos Python de dbt, así que el resto sigue en Python. Hay que comprobarlo antes de comprometerse.

## Orden de ejecución

| Hito | Contenido | Hecho cuando |
|---|---|---|
| H1 · Diseño | contratos de dynamics, palancas y registro; carpetas; esquemas SQL | documento revisado |
| H2 · Etapa 0 | raw validado y persistido por corte; los pasos 1.1–1.4 leen de él | el framework actual corre sobre el raw persistido con los mismos números |
| H3 · Primera dynamic: curvas de maduración | `aprender(raw, a_fecha)`; la caja `StateMaturation` lee la dynamic; examen a fecha de origen | test de igualdad bien; plantilla para el resto |
| H4 · Transiciones y calendario de subidas | misma plantilla | test de igualdad bien |
| H5 · Registro de ejecuciones y referencia congelada | `sff_ejecuciones`; salidas por `run_id`; congelar la entregada | se puede comparar la realidad del mes con la referencia |
| H6 · Palancas | fichero de palancas; aplicación en el núcleo; columnas de efecto; descomposición baseline + palancas | un escenario «campaña cancel DACH» corre sin recalcular 0–2 |
| H7 · Seguimiento | realidad frente a referencia, baseline y escenario; resultado por palanca; deriva de las dynamics | informe mensual de seguimiento |
| H9 · What if sobre las dynamics | ver abajo | un escenario «softcancel de DACH −20 %» cambia el forecast sin tocar la dynamic aprendida |
| H8 · Limpieza | sacar del núcleo lo que queda de análisis (veredictos, perfil, informe) a las etapas 1 y 4; quitar del informe (cap. 1, 8.2, 8.5, 8.9, 8.10), del perfil de datos (8.6) y de los informes en pantalla del bloque 1 lo que ya describe la etapa 1 | el núcleo solo predice y examina; nada se describe dos veces |

H2 y H3 son los que más tiempo ahorran. H6 y H7 son los que dan el valor de negocio: acordar palancas y medir si ganan a la baseline.

## Revisión de la misión de cada etapa (28-oct-2026)

Miguel Angel revisa la misión de cada etapa en pocas palabras, una a una, para ver si está alineada con lo que tiene en la cabeza. Lo que sale de cada revisión se anota aquí para implementarlo.

### Etapa 0 · Datos (hecho el 28-oct-2026)

1. **El dato es la pipeline, no «el extracto de renovaciones».** Es como se llama dentro de la compañía: la pipeline pasada, con su resultado (lo renovado, su performance), y la pipeline futura, que aún no tiene resultado. El código, el log y los documentos de la etapa 0 hablan de «la pipeline».
2. **Fuera lo superfluo.** La query está montada sobre un sistema robusto y Miguel Angel es el responsable de que se alimente con los datos correctos. Se quitan:
   - la comparación de la historia con la carga anterior (el 0,5 %) y el resumen mensual que la alimentaba;
   - la ficha (corte, filas, huella de la query) y sus avisos;
   - la comprobación de ida y vuelta (lo guardado = lo leído): los cambios del código se controlan con los tests.
3. **Se queda lo necesario para que las cuentas funcionen:** las pruebas de estructura y valores de los pasos 1.1 y 1.2 (cada columna con su papel, los datos de la forma correcta), y guardar el dataset con el tipo de cada columna.
4. **«Corte» es impreciso.** Significa el mes en curso de la ejecución (2026-10): los meses anteriores son historia cerrada y desde él empieza la pipeline futura. En los textos, «mes en curso».

### Etapa 1 · Análisis (hecho el 28-oct-2026)

Lo que pidió Miguel Angel y está en `stage_1_analysis.py`: todo lo que describe el raw va aquí, con tablas, resúmenes numéricos y gráficos de evolución en el tiempo:
- la pipeline real y sus biorritmos: si crece frente al año anterior, cuánto dinero tiene, la proporción de 1, 2 y 3 años, la tendencia de lo que ya conocemos por los meses conocidos;
- el último mes cerrado frente al mismo mes del año anterior (octubre contra octubre): dónde están las diferencias, por dimensión;
- la adquisición y su tendencia; la composición y si cambia;
- la tasa de renovación, la revalorización y las subidas de precio que ha habido;
- KPIs derivados: el softcancel en el primer mes (y en los dos primeros) de cada cohorte, y lo visible hoy frente a hace un año al mismo horizonte;
- una recta de regresión sobre lo que debería ser estable: pendiente y si es significativa, más la estacionalidad.

Lo que ya estaba en otros sitios (capítulo 1 del informe, 8.2, 8.5, 8.9, 8.10, el perfil de datos de 8.6, los informes del raw en pantalla del bloque 1) **sigue ejecutándose** y lleva una nota en su cabecera: se retira en H8.

## Anotado para más adelante · el what if sobre las forecast dynamics (28-oct-2026)

**La idea:** una dynamic aprendida (la maduración, por ejemplo) también sirve para preguntar «¿qué pasaría si…?»: si una campaña bajara la cuota final de softcancel de una región, ¿cuánto cambiaría el forecast? Es un uso secundario de las dynamics, separado de su uso principal (predecir), y de momento no lleva un nombre propio.

**Lo que hay hoy no lo permite.** La dynamic guardada es un registro: la caja se reconstruye desde los datos y de la ficha solo toma la decisión de usar o rechazar cada curva. Editar las tablas `sff_fd_*` no cambia el forecast.

**Dos caminos:**
1. que el núcleo lea los valores guardados de la dynamic, de modo que editarlos cambie el forecast;
2. **(preferido)** un fichero de ajustes sobre la dynamic, por ejemplo «cuota final de softcancel × 0,8 en DACH», aplicado al construir la caja. La dynamic aprendida no se toca y el ajuste queda escrito aparte, con quién lo acordó y cuándo, como las palancas de hoy.

Las palancas de hoy (ajustes directos de tasa y revalorización en el 7.2) se quedan como están; pueden acabar siendo ese fichero de ajustes. El examen del 7.1 nunca lleva ajustes.

## Pendiente antes de empezar

- Sacar el resultado de este mes con el framework actual. Antes, poner `TERM_TRANSITION_COLUMNS_IN_EXTRACT = True` cuando el extracto traiga las seis columnas.
- Revisar con datos reales:
  - la bajada de pipeline de Europa (7.2);
  - lo que falta en 7.3b;
  - las subidas detectadas (8.9).
- Mejoras ya anotadas, que encajan en el plan:
  - identificar la pipeline de retail to subscription (etapa 0);
  - revisar el nivel de retail to subscription (etapa 2).
