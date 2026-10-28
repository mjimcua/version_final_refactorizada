# GUÍA · La prueba con datos reales (28-oct-2026)

Qué hacer, en qué orden y qué mirar en la primera ejecución con el extracto real de esta versión.

## Antes de empezar

1. **`entorno_local.py`**, el tuyo de siempre, no viaja en el zip: el servidor, la base, el schema y la query del extracto. Si quieres fijar el corte, `CURRENT_MONTH`.
2. **El extracto del 28-oct** ya trae las seis columnas de transición de plazo y `dormant_month_0…12`. `main.py` está preparado:
   - `TERM_TRANSITION_COLUMNS_IN_EXTRACT = True`;
   - `maturation_dims=["softcancel", "dormant"]`.
3. **Sin `palancas.csv`** en la carpeta, el forecast es el del método. Para la primera prueba, mejor sin palancas.

## Las ejecuciones, en este orden

| # | Comando | Qué hace | Cuándo |
|---|---|---|---|
| 1 | `python main.py` | etapa 0 (lee la pipeline con su SQL, la prueba y la guarda) + **etapa 1 (el análisis de la pipeline)** + aprende las forecast dynamics + forecast; queda registrada como **baseline** | una vez por corte |
| 2 | `python ejecutar_informe.py` | el informe entero sobre las tablas de la 1, sin volver a ejecutar el forecast (o, de una vez, `python main.py informe` en la 1) | después de la 1 |
| 3 | `python main.py escenario` | un escenario: sin SQL, sin análisis y sin volver a examinar la curva de maduración; con `palancas.csv`, sus palancas | todas las veces que quieras dentro del mes |
| — | `python main.py solo_analisis` | solo la etapa 1 sobre el dataset guardado: `sff_e1_*` y `salida/analisis/ANALISIS_pipeline.md` | cuando quieras volver a mirar la pipeline |
| 4 | `python main.py referencia` | la que entregas a negocio: se registra y **se congela** | cuando entregues |

El mes que viene, la pregunta 9.2 del informe comparará la realidad con la referencia que congeles ahora. Si no congelas ninguna, no habrá con qué comparar.

**Con `sin_datos` o `escenario`** se usa el último dataset escrito, sea del mes que sea: el mes siguiente, ejecuta antes la etapa 0.

## Qué mirar en el log (`salida/sff_ejecucion.log`)

| Línea | Qué buscar |
|---|---|
| `[E0] … checks:` | las pruebas de valores del paso 1.2 sobre la pipeline, sin fallos |
| `[E0] ▸ 4. dataset written` | cuánto tarda en guardar la pipeline en SQL Server: es el coste de la etapa 0, una vez al mes |
| `[E1] ▸ 2.` … `▸ 12.` | las acciones del análisis: el dinero de cada año y su crecimiento, el mes cerrado contra el mismo mes del año anterior, las subidas detectadas, los KPIs con tendencia; al final, la VALORACIÓN en una página (la misma que abre `ANALISIS_pipeline.md`) |
| `[4.1] VALORACIÓN dormant` / `DECISIÓN dormant` | si la curva de dormant aprueba su examen. Si no, toma su proporción histórica, como hasta ahora |
| `[7.2] … term transitions` | de qué plazos vienen las renovaciones proyectadas |
| `[7.2] VALORACIÓN 2027` | el forecast con los estados de hoy y con la maduración |
| `[E2] forecast dynamic 'maduracion_estados' persisted` | la dynamic guardada (con `escenario` saldrá `[E2] … checks: 2 ok`) |
| `[E5] run … registered` | la ejecución en el registro, con sus totales |

## Qué revisar en el análisis (`salida/analisis/ANALISIS_pipeline.md`)

Es la primera vez que se ejecuta sobre datos reales. Lo que más interesa:
- **En una página:** si cuadra con lo que sabes de la pipeline (el crecimiento sobre meses comparables, la tasa de los últimos 12 meses, la revalorización).
- **Mes contra mes:** el último mes cerrado frente al mismo mes del año anterior, y dónde están las diferencias por región y producto.
- **La adquisición por mes de venta** (licencias de 1 año): la tendencia y el ritmo de cada año.
- **Los estados tempranos:** la parte de cada cohorte ya en softcancel (y dormant) en su primer mes de vida, y los meses que vienen frente a hace un año al mismo horizonte.
- **Las tendencias:** la tabla final; si una serie que debería ser estable sale «sube» o «baja», mira su gráfico.

## Qué revisar en el informe

- **7.2:** la bajada de pipeline de Europa.
- **7.3b:** lo que le falta a la proyección de renovaciones.
- **8.9:** las subidas de precio detectadas frente a las tarifas que se hicieron.
- **8.10:** a qué plazo renuevan las licencias, ahora que el extracto trae las columnas.
- **9.1:** cuánto cambia 2027 por la adquisición de 2026. Si sale el AVISO de la adquisición simulada, el descuento con que se simula (`acquisition_discount`, 40 %) no es el real, y la revalorización de octubre a diciembre sale inflada o corta: dímelo con el descuento real que veas en el anexo.

## Si algo se para

| Mensaje | Qué hacer |
|---|---|
| `step 1.1 · VALIDATE RAW: … columns with no role` | una columna nueva del extracto: dime cuál y su papel |
| `no dataset written` | has lanzado `sin_datos` o `escenario` sin ninguna etapa 0: ejecuta `python main.py` |
| `the dynamic was learned from what this run would learn from … differences` | la dynamic es de otros datos o de otra Config: `python main.py sin_datos`, que aprende de nuevo sin volver a lanzar la SQL |
| `the levers file … has N problems` | el fichero de palancas: el mensaje dice cada problema |

## Tablas nuevas en SQL Server

Si ya habías ejecutado la versión anterior, las tablas `sff_s2_maduracion_*`, `sff_e0_resumen_mensual` y `sff_e0_ficha` se quedan huérfanas: con el nombre nuevo (`sff_fd_*`) la primera ejecución vuelve a aprender. Puedes borrarlas.

| Tabla | Cómo se escribe |
|---|---|
| `sff_e0_dataset`, `sff_e0_dataset_manifiesto` | etapa 0, se reemplazan en cada carga |
| `sff_e1_*` (16 tablas, las que tengan datos: pipeline por mes y por año, mes contra mes, plazo, tasa, uplift, subidas, adquisición, composición, estados, tendencias…) | etapa 1, se reemplazan en cada análisis |
| `sff_fd_maduracion_ficha`, `_examen`, `_curva`, `_por_region` | forecast dynamic de la maduración, se reemplazan al aprender |
| `sff_palancas_aplicadas` | paso 7.2, se reemplaza |
| `sff_ejecuciones`, `sff_ejecucion_foto`, `sff_ejecucion_referencias` | registro: **solo crecen** |

## La prueba previa (hecha aquí, 28-oct-2026)

Se ha ejecutado la Config de producción de `main.py` de principio a fin, con un `entorno_local` de prueba, sobre SQLite y con el sintético parecido al real más `dormant_month_0…12`.

| Ejecución | Resultado |
|---|---|
| `python main.py informe` | etapa 0, forecast dynamics, forecast, registro (baseline) e informe completo: responde todas las preguntas menos la 9.2, que aún no tiene referencia (y lo dice) |
| `python main.py escenario` con tres palancas (dos acordadas y una propuesta) | se aplican las dos acordadas (+$451.888 de efecto directo en 2027) y la propuesta no; se registra como escenario con su nota; 2027 queda en la baseline + el efecto directo |
| `python main.py referencia` | se registra y se congela: queda en `sff_ejecucion_referencias` |

**Avisos que en la prueba son del sintético, no del código:**
- 5.1: los objetivos de adquisición reales sobre volúmenes sintéticos, unas 10 veces mayores;
- regiones de los objetivos que el sintético no tiene;
- 8.4: claves de Power BI.

Con tus datos, esos avisos tienen que leerse de verdad.

**Tests:** 32 ficheros, todos pasan.
