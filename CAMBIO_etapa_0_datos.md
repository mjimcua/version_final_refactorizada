# CAMBIO · Etapa 0 · datos, y un `main` por etapas (28-oct-2026)

Primer paso del plan de etapas (`PLAN_etapas.md`, hito H2). **Simplificada el mismo día** tras la revisión de su misión: se quitan la comparación de la historia con la carga anterior, la ficha (corte, filas, huella de la query), el resumen mensual y la comprobación de ida y vuelta.

## Misión

Dejar la pipeline del mes en curso leída, probada y guardada, para que todo lo que se calcula ese mes salga del mismo dato. La pipeline es la pasada, con su resultado (lo renovado), y la futura, que aún no tiene resultado.

## Qué hace (`stage_0_data.py`)

1. Lee la pipeline con el `read_raw` de la Config. En producción es la SQL de `entorno_local.py`.
2. Prueba que trae lo que el framework necesita para que las cuentas funcionen:
   - **estructura (paso 1.1):** cada columna tiene su papel en la Config y los meses aguantan el calendario;
   - **valores (paso 1.2):** los dos universos, el dinero sin nulos ni negativos, lo renovado coherente con lo que vence, las dimensiones nunca vacías y las marcas 0 / 1.

   Si una prueba falla, se para y no escribe nada.
3. La guarda tal cual se leyó, con el tipo de cada columna para que vuelva igual.

| Tabla | Qué guarda |
|---|---|
| `sff_e0_dataset` | la pipeline tal cual se leyó |
| `sff_e0_dataset_manifiesto` | cada columna y su tipo |

Si ya habías ejecutado la versión anterior, `sff_e0_resumen_mensual` y `sff_e0_ficha` se quedan huérfanas y puedes borrarlas.

## Cómo se usa

| Comando | Qué ejecuta |
|---|---|
| `python main.py` | etapa 0 + forecast |
| `python main.py sin_datos` | el forecast sobre el dataset guardado: no lanza la SQL |
| `python main.py solo_datos` | solo la etapa 0 |
| `python main.py informe` | además, el informe al acabar |

En `main.py`: `RUN_STAGE_0_DATA = True / False`. En un notebook: `run_stages(configuracion, StagesToRun(data=False))`.

Sin etapa 0, el forecast lee el dataset guardado. Si no hay ninguno, se para y dice que se ejecute la etapa 0. **Qué dataset se usa es responsabilidad de quien ejecuta:** `sin_datos` lee el último escrito, sea del mes que sea. El mes siguiente hay que ejecutar la etapa 0 antes.

## Comprobado

**`test_stage_0_data.py`**, 13 comprobaciones:
- la etapa 0 escribe sus dos tablas tras las pruebas de 1.1 y 1.2; una pipeline con un USD negativo se para y no escribe nada;
- el dataset vuelve igual que la pipeline leída: mismos tipos y mismos valores (también en CSV, sin motor SQL);
- **el forecast sobre el dataset guardado es el mismo que sobre la pipeline**: por mes, por año y el examen;
- sin dataset, se para y lo dice;
- las etapas de `main` y las palabras de la línea de comandos.

## Lo que no cambia

- Los números del forecast.
- `main.run()`.
- El bloque 1, que sigue ejecutándose entero sobre el dataset.
