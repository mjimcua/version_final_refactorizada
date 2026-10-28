# CAMBIO · Las palancas: lo acordado con negocio, aplicado al forecast como escenario (28-oct-2026)

Hito H6 del plan de etapas (`PLAN_etapas.md`).

## En una frase

Un fichero `palancas.csv` recoge lo que acuerdas con los retention managers, por ejemplo «campaña sobre los softcancel de DACH de marzo a agosto, +3 pp de tasa». El forecast lo aplica sobre lo que ha aprendido. Cada fila dice qué palancas la movieron y cuánto, y la ejecución se registra como escenario junto a su baseline.

## Cómo se usa

1. Copia `palancas_ejemplo.csv` a `palancas.csv`, junto a `main.py`, y edítalo. Con `palancas.csv` en la carpeta, `main.py` lo usa; sin él, el forecast es el del método.
2. Pon `estado = acordada` en las palancas que se aplican. Las `propuesta` y `descartada` se quedan en el fichero como registro, pero no se aplican (`levers_states`).
3. Ejecuta `python main.py escenario` (sin SQL y sin volver a aprender). La ejecución queda en `sff_ejecuciones` con sus palancas y su efecto. Una ejecución con palancas nunca queda registrada como baseline.

## El fichero

Separado por `;` o `,`, con una fila por palanca:

| Columna | Ejemplo |
|---|---|
| `id` | `P-2027-01` |
| `descripcion` | Campaña de recuperación de cancel en DACH |
| `acordado_con`, `fecha_acuerdo` | retention manager DACH · 2026-11-10 |
| `estado` | `propuesta` · `acordada` · `descartada` |
| `ambito` | `tr_regional_level_3=DACH & softcancel=1` (vacío = toda la cartera) |
| `desde`, `hasta` | `2027-03` · `2027-08` (meses de vencimiento, ambos incluidos) |
| `tipo` | `tasa_suma_pp` · `tasa_multiplica` · `uplift_multiplica` · `uplift_suma` |
| `valor` | `3` |

**El ámbito**, separado por `&`, porque `;` y `,` son de las columnas del CSV:
- `columna=valor & columna=valor1|valor2`;
- puede usar las dimensiones, los estados del cliente (`softcancel=1`) y `origen_pipeline` (`real`, `proyectada` o `simulada`).

## Dónde se aplica

**Solo en el forecast (paso 7.2), nunca en el examen del 7.1**: el examen mide el método, no la campaña. Se aplica a:
- las filas futuras del extracto;
- las renovaciones proyectadas y la adquisición simulada de la ventana;
- las filas de la maduración de los estados.

**Cómo mueve cada palanca:**
- la tasa queda en [0, 1] y su banda se mueve con ella;
- la revalorización también mueve su banda;
- una palanca en los meses de la ventana (del mes en curso a diciembre) también mueve el año que viene, porque lo que renueva de más vuelve a vencer.

**Cada fila guarda**, en el núcleo como `s7_2_palancas` y `s7_2_efecto_palanca_usd`:
- las palancas que la movieron;
- la tasa y la revalorización que tenía antes de ellas;
- su **efecto directo**: lo esperado menos la misma fila sin palancas.

La pipeline que una palanca de este año añade al año que viene no está en el efecto directo, sino en el total. Por eso hay que compararlo con la baseline del registro.

**`sff_palancas_aplicadas`:** una fila por palanca del fichero, con si se aplicó, las filas y el USD que tocó, y su efecto directo por año.

## Comprobaciones

- Si el fichero tiene problemas (un mes que no lo es, un tipo desconocido, un valor que no es un número, un id repetido, un ámbito sin valor), **se para y los nombra todos a la vez**.
- Una palanca que se aplica pero no toca ninguna fila es un aviso, con su id: su ámbito o sus meses no encajan con nada.
- La auditoría (8.2) compara la técnica con la tasa **antes** de las palancas, porque las palancas la mueven a propósito.

## Comprobado

**`test_levers.py`**, 15 comprobaciones:
- **una palanca de tasa:**
  - las filas de su ámbito y sus meses suben los pp indicados, con su banda, y las demás no;
  - el efecto directo es lo esperado menos la fila sin palanca;
  - el total del año de la palanca sube exactamente su efecto directo, y el otro año no se mueve;
- **una palanca en la ventana:**
  - 2026 sube su efecto directo;
  - las renovaciones proyectadas de 2027 crecen ($88.847 → $93.722 en el sintético);
- el examen del 7.1 es idéntico con y sin palancas;
- solo se aplican las `acordada`, y una palanca que no toca nada da aviso;
- un fichero con problemas los nombra todos;
- una ejecución con palancas se registra como escenario con sus ids y su efecto;
- una palanca de revalorización multiplica el uplift de su ámbito.

## Lo que viene

- **El seguimiento por palanca:** en la 9.2, la realidad del ámbito y los meses de cada palanca frente a la baseline. Así se sabe si la campaña ganó a la baseline donde se aplicó.
- **Más tipos de palanca**, si los necesitas. Por ejemplo, el volumen de la adquisición simulada o la cuota final de un estado (la maduración).
