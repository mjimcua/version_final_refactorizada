# CAMBIO · El registro de ejecuciones y la referencia congelada (28-oct-2026)

Hito H5 del plan de etapas (`PLAN_etapas.md`). Es la base de la etapa 5, el seguimiento.

## En una frase

Cada forecast deja una fila y una foto de su resultado que no se borran nunca. El forecast que entregas a negocio se congela como referencia, para poder seguir después la realidad frente a él.

## Por qué

Las tablas de una ejecución (`sff_nucleo`, `sff_forecast_mes`…) las reemplaza la siguiente. Para comparar la realidad con lo entregado, la baseline con un escenario o un escenario con otro, hace falta lo que cada uno dijo en su día y con qué entradas. Esto es lo que lo guarda, añadiendo filas y sin reemplazar nada.

## Cómo se usa

| Comando | Tipo en el registro |
|---|---|
| `python main.py` | `baseline` |
| `python main.py escenario` | `escenario` (sin SQL y sin volver a aprender) |
| `python main.py referencia` | `referencia`: la ejecución se registra **y se congela** |

En `main.py`:
- `RUN_KIND = "baseline"`;
- `RUN_NOTE = "campaña cancel DACH +3 pp"`: lo que es esta ejecución, en una línea.

En un notebook:

```python
from runs import freeze_the_reference, the_reference
freeze_the_reference(configuracion, "20261028-183104-123456", "la que se entregó")   # congelar una ejecución anterior
referencia, foto = the_reference(configuracion)        # la última referencia congelada de este corte y su foto
```

## Qué se guarda (se añade, nunca se reemplaza)

| Tabla | Qué es |
|---|---|
| `sff_ejecuciones` | una fila por ejecución (detalle abajo) |
| `sff_ejecucion_foto` | por ejecución, el resultado al grano en que lo lee negocio (detalle abajo) |
| `sff_ejecucion_referencias` | una fila por referencia congelada: `run_id`, corte, cuándo se congeló y la nota |

**Cada fila de `sff_ejecuciones` lleva:**
- el `run_id` (fecha y hora al microsegundo), el corte, el tipo, la nota y cuándo se escribió;
- las etapas que se ejecutaron;
- la forecast dynamic de maduración que usó (cuándo y su huella);
- la huella del código, para saber si dos ejecuciones corrieron el mismo código;
- el total del año en curso y del siguiente, con la banda del examen;
- los segundos que tardó.

**`sff_ejecucion_foto`**, por ejecución:
- el grano: mes × las dimensiones de `run_snapshot_dims` (vacío = los dos niveles de región y el plazo) × universo × origen de la pipeline × estado (real o forecast);
- las medidas: unidades y USD que vencen, unidades y USD renovados;
- los meses: del año en curso a diciembre del siguiente.

**Congelar** es añadir una fila a `sff_ejecucion_referencias` que apunta a la ejecución. Su fila y su foto se quedan como se escribieron. La referencia de un corte es la última que se congeló.

Sin motor SQL no se registra nada y el log lo dice: el registro vive en SQL.

## Comprobado

**`test_runs.py`**, 10 comprobaciones:
- una ejecución se registra con sus entradas y sus totales, que coinciden con `sff_resumen_negocio`;
- su foto tiene el dinero del núcleo;
- una segunda ejecución añade su fila y su foto, y la primera no cambia;
- una ejecución de tipo `referencia` se congela;
- una ejecución anterior se puede congelar por su id, y la última congelada es la referencia;
- una ejecución que no existe se rechaza;
- sin motor no se registra;
- las palabras `escenario` y `referencia` ponen el tipo.

## Lo que viene

**H7, el seguimiento.** La primera pieza ya está: la pregunta 9.2 del informe compara la realidad de los meses cerrados con la foto de la referencia y con la baseline de su corte, y reparte la diferencia en pipeline y rendimiento (`CAMBIO_informe_forecast.md`, §9.2).

Falta el seguimiento de los patrones: si la tasa, la revalorización y la maduración se desvían de las forecast dynamics.

**H6, las palancas.** Los escenarios con ajustes (por ejemplo, una campaña de cancel) se registran como `escenario` con su nota. El seguimiento podrá decir entonces si la campaña ganó a la baseline.
