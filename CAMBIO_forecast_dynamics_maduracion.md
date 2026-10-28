# CAMBIO · Etapa 2 · la primera forecast dynamic: la maduración de los estados del cliente (28-oct-2026)

Hito H3 del plan de etapas (`PLAN_etapas.md`). Renombrado el 28-oct-2026: lo que aquí se llamaba «supuesto aprendido» es una **forecast dynamic** (`assumptions.py` → `forecast_dynamics.py`, `sff_s2_maduracion_*` → `sff_fd_maduracion_*`).

## En una frase

Lo que el paso 4.1 aprende y decide (la curva de maduración de cada estado fechado, su examen y si se usa o se rechaza) se guarda como forecast dynamic con su ficha. Un escenario del mismo mes lo lee en lugar de volver a examinar la curva, y el forecast sale igual.

## El nombre

Una **forecast dynamic** es un patrón que el forecast aprende del pasado y aplica para predecir: la maduración de los estados, las transiciones de plazo, el calendario de subidas. El ciclo es:

| | Qué | Dónde |
|---|---|---|
| Aprender del pasado | la dynamic se mide y se guarda con su ficha | etapa 2 |
| Aplicarla en el presente | el núcleo la lee para predecir y rellenar los huecos | etapa 3 |
| Confirmarla con el futuro | ¿se cumplió? Si no, se recalibra o se busca cambiarla | etapa 5, seguimiento |

«Insights» queda para lo que el análisis cuenta a negocio, que no tiene por qué alimentar el núcleo.

El paso 2.5 («Dinámica de la tasa»: autocorrelación, tendencia y estacionalidad de cada serie) conserva su nombre: es la dynamic de la tasa, una más bajo el mismo paraguas, aunque hoy no se guarda en la etapa 2.

## Por qué así

Lo caro del paso 4.1 no es la caja (`StateMaturation` aprende su mezcla y sus curvas en 1,6 s en el sintético parecido al real), sino el **examen de la curva**: cada mes de examen por cada horizonte vuelve a aprender una curva. Son unos 30 s de los 37 s del paso con un estado fechado, y con dormant fechado se duplica. Ese examen toma una **decisión**: una curva que no lo pasa no se usa.

Por eso la dynamic guarda la decisión y lo aprendido, y al leerlo la caja se vuelve a construir desde la tabla fina con el mismo código. Así el resultado es idéntico por construcción, y el examen del 7.1 sigue aprendiendo «a fecha de cada origen» con la misma clase: sigue siendo honesto.

## Cómo se usa

| Comando | Qué hace |
|---|---|
| `python main.py` | etapa 0 + aprende las forecast dynamics (las guarda) + forecast |
| `python main.py sin_aprender` | el forecast con las dynamics guardadas de este corte |
| `python main.py escenario` | `sin_datos` + `sin_aprender`: un escenario del mes sin SQL y sin volver a examinar la curva |

En `main.py`: `RUN_STAGE_2_LEARNING = True / False`. En un notebook:

```python
run_stages(configuracion, StagesToRun(data=False, learning=False))
```

## Qué se guarda

| Tabla | Qué es |
|---|---|
| `sff_fd_maduracion_ficha` | corte, fecha a la que se aprendió, estados, estados fechados, curvas usadas y rechazadas con sus errores, y la huella de lo aprendido |
| `sff_fd_maduracion_examen` | el examen de la curva de cada estado fechado, por horizonte |
| `sff_fd_maduracion_curva` | la curva de la cartera de cada estado fechado: lo visible del estado final k meses antes, p(k) y si se usa |
| `sff_fd_maduracion_por_region` | la maduración de cada estado por región (acción 3 del paso 4.1) |

**La huella** de lo que se aprendió:
- el corte;
- los meses cerrados de la ventana: filas, unidades que vencen y unidades en cada estado;
- los meses de examen;
- cada campo de la Config que lee el paso 4.1 (en `forecast_dynamics.py`, salvo los que solo dicen qué se enseña).

## Cuándo se para

Al leer la dynamic, el forecast se para y dice qué ha cambiado en estos casos:
- no hay dynamic guardada;
- su huella no coincide con la ejecución: otro corte, otros meses cerrados (una recarga), otros meses de examen o un campo del paso 4.1 cambiado (por ejemplo `maturation_min_units`);
- se aprendió con otra versión del método.

En todos, la salida es aprender otra vez: `RUN_STAGE_2_LEARNING = True`.

## Lo que no cambia

- Los números.
- El examen honesto del 7.1: sigue reconstruyendo la caja en cada origen.
- `main.run()`: aprende y guarda, como hasta ahora.

## Comprobado

**`test_forecast_dynamics.py`**, 16 comprobaciones, con un sintético que trae `softcancel_month_0…12`:
- aprender escribe la ficha, el examen, la curva y la maduración por región;
- **el forecast con la dynamic leída es el mismo** (por mes, por año y el examen del 7.1), sin ejecutar el paso 4.1;
- una curva rechazada por su examen sigue rechazada al leerla;
- se para sin dynamic, con otro corte, con un campo de la Config cambiado y con meses cerrados que cambiaron;
- las etapas y las palabras `sin_aprender` y `escenario`.

**Siguen pasando** `test_8_4_power_bi.py`, `test_pipeline.py` y `test_stage_0_data.py`.

**Sintético parecido al real** (corte 2026-10, softcancel fechado):

| | Aprende (`sin_datos`) | Escenario (`escenario`) |
|---|---|---|
| Paso 4.1 | 35,0 s: aprende, examina la curva y la guarda (2,7 s) | 3,7 s: comprueba la ficha y reconstruye la caja |
| Forecast 2026 | $7.243.191 | $7.243.191 |
| Forecast 2027 | $24.799.068 | $24.799.068 |
| Forecast (bloques 1 a 8) | 345 s | 295 s |

En producción, con softcancel y dormant fechados y más filas, el ahorro del 4.1 es mayor.

## Lo que viene

**Lo guardado es un registro, no una entrada.** La caja se reconstruye desde los datos y de la ficha solo toma la decisión de usar o rechazar cada curva. Editar la curva o la cuota final en las tablas guardadas no cambia el forecast. El *what if* sobre una dynamic («¿y si los softcancel de DACH fueran un 20 % menos?») está anotado en `PLAN_etapas.md` para más adelante.

Con la misma plantilla (ficha, huella, decisión guardada y reconstrucción con el mismo código), las siguientes candidatas son:
- **la decisión del backtest de la tasa** (paso 2.6, unos 30 s): la técnica de cada composición y su banda;
- **el calendario de subidas de precio** y **las transiciones de plazo**: son baratos, pero los quieres ver y retocar como dynamics;
- **el what if sobre las dynamics** (anotado en el plan).
