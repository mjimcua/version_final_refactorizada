"""
levers.py — THE LEVERS: what is agreed with the business and is not in the data, applied to the forecast as a scenario
(28-oct-2026, PLAN_etapas.md, milestone H6).

MISSION: the forecast says what happens if nothing changes. A lever says what is agreed to change: "a campaign on the
softcancels of DACH from March to August, +3 pp of rate". It is not data, and it does not have to be: it is an
adjustment agreed with a retention manager, written down with who agreed it and when. The forecast applies it on top
of what it learned, and every row says which levers moved it and by how much. The register of runs (runs.py) keeps the
scenario next to its baseline, and the report (9.2) says later whether reality beat the baseline.

THE FILE (levers_file, a CSV with ; or , as separator; one row per lever):
  id              a short name, unique (P-2027-01)
  descripcion     what the lever is (campaña de recuperación de cancel en DACH)
  acordado_con    who agreed it (retention manager DACH)
  fecha_acuerdo   when (2026-11-10)
  estado          propuesta · acordada · descartada: only the states of levers_states are applied (acordada)
  ambito          where it applies: column=value & column=value|value … over the columns of the future rows (the dims,
                  the customer states, origen_pipeline = real · proyectada · simulada). Empty = every row
  desde, hasta    the due months it applies to (YYYY-MM, both included)
  tipo            what it changes:
                    tasa_suma_pp       the renewal rate + valor percentage points (its band moves with it)
                    tasa_multiplica    the renewal rate × valor
                    uplift_multiplica  the uplift × valor (its band too)
                    uplift_suma        the uplift + valor
  valor           the number

WHERE IT IS APPLIED: step 7.2 only (predict_rows: the future rows of the extract, the projected renewals and the
simulated acquisitions of the window, the rows of the maturation of the states), never in the exam of step 7.1: the
exam measures the method, not the campaign. A lever on the months of the window (current month to December) also
moves the pipeline of next year: what renews more falls due again. The rate stays in [0, 1] and every band keeps its
width.

WHAT EVERY ROW CARRIES: palancas (the ids of the levers that moved it), tasa_sin_palanca and uplift_sin_palanca (what
the forecast had before), efecto_palanca_usd (expected USD − the same row without the levers: the DIRECT effect; the
pipeline that a lever of this year adds to next year is in the total, not in that column). In sff_nucleo:
s7_2_palancas and s7_2_efecto_palanca_usd. Step 7.2 writes sff_palancas_aplicadas: one row per lever of the file, with
whether it was applied, the rows and the USD due it touched and its direct effect by year.

THE INTERFACE:
  levers = read_the_levers(configuration)                 the file, checked (an empty table when there is none)
  rows = apply_the_levers(rows, levers, configuration)    inside predict_rows (step 7.2)
  table = levers_applied(future, levers, configuration)   the summary of every lever, for sff_palancas_aplicadas
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import numpy as np
import pandas as pd

from config import DUE_USD_AT_DUE_COLUMN, Config

# ─── named constants ─────────────────────────────────────────────────────────────
LEVER_COLUMNS = ["id", "descripcion", "acordado_con", "fecha_acuerdo", "estado", "ambito", "desde", "hasta", "tipo", "valor"]
LEVER_TYPES = {"tasa_suma_pp": "the rate + valor pp", "tasa_multiplica": "the rate × valor",
               "uplift_multiplica": "the uplift × valor", "uplift_suma": "the uplift + valor"}
LEVER_STATES = ("propuesta", "acordada", "descartada")
LEVERS_COLUMN = "palancas"
RATE_BEFORE_LEVERS = "tasa_sin_palanca"
UPLIFT_BEFORE_LEVERS = "uplift_sin_palanca"
LEVER_EFFECT_COLUMN = "efecto_palanca_usd"
SCOPE_SEPARATOR, VALUE_SEPARATOR = "&", "|"        # not ; nor ,: they separate the columns of the CSV


# ═══════════════════════════════════════════════════════════════════════════════════
# READ AND CHECK THE FILE
# ═══════════════════════════════════════════════════════════════════════════════════

def read_the_levers(configuration: Config) -> pd.DataFrame:
    """The levers of levers_file, checked: every column there, unique ids, known states and types, months and numbers
    that read. Stops naming every problem at once. An empty table when the Config has no file."""
    if not configuration.levers_file:
        return pd.DataFrame(columns=LEVER_COLUMNS + ["aplicar", "_desde", "_hasta", "_ambito"])
    levers = pd.read_csv(configuration.levers_file, sep=None, engine="python", dtype=str, keep_default_na=False)
    levers.columns = [str(column).strip().lower() for column in levers.columns]
    problems = [f"missing columns {sorted(set(LEVER_COLUMNS) - set(levers.columns))}"] if set(LEVER_COLUMNS) - set(levers.columns) else []
    if problems:
        raise ValueError(f"the levers file {configuration.levers_file}: " + "; ".join(problems))
    levers = levers[LEVER_COLUMNS].apply(lambda column: column.str.strip())
    levers = levers[levers["id"] != ""].reset_index(drop=True)
    repeated = sorted(levers.loc[levers["id"].duplicated(), "id"])
    if repeated:
        problems.append(f"repeated ids {repeated}")
    for _, lever in levers.iterrows():
        name = lever["id"]
        if lever["estado"] not in LEVER_STATES:
            problems.append(f"{name}: estado '{lever['estado']}' is not one of {list(LEVER_STATES)}")
        if lever["tipo"] not in LEVER_TYPES:
            problems.append(f"{name}: tipo '{lever['tipo']}' is not one of {list(LEVER_TYPES)}")
        try:
            float(lever["valor"].replace(",", "."))
        except ValueError:
            problems.append(f"{name}: valor '{lever['valor']}' is not a number")
        for column in ("desde", "hasta"):
            try:
                pd.Period(lever[column], freq="M")
            except (ValueError, TypeError):
                problems.append(f"{name}: {column} '{lever[column]}' is not a month (YYYY-MM)")
        try:
            parse_scope(lever["ambito"])
        except ValueError as error:
            problems.append(f"{name}: {error}")
    if problems:
        raise ValueError(f"the levers file {configuration.levers_file} has {len(problems)} problems:\n  "
                         + "\n  ".join(problems))
    levers["valor"] = levers["valor"].str.replace(",", ".").astype(float)
    levers["_desde"] = [pd.Period(text, freq="M") for text in levers["desde"]]
    levers["_hasta"] = [pd.Period(text, freq="M") for text in levers["hasta"]]
    levers["_ambito"] = [parse_scope(text) for text in levers["ambito"]]
    levers["aplicar"] = levers["estado"].isin(configuration.levers_states)
    return levers


def parse_scope(text: str) -> dict:
    """'tr_regional_level_3=DACH & softcancel=1' → {'tr_regional_level_3': ['DACH'], 'softcancel': ['1']}."""
    scope = {}
    for part in [part.strip() for part in str(text).split(SCOPE_SEPARATOR) if part.strip()]:
        if "=" not in part:
            raise ValueError(f"ambito '{part}' is not column=value")
        column, values = (piece.strip() for piece in part.split("=", 1))
        if not column or not values:
            raise ValueError(f"ambito '{part}' has no column or no value")
        scope[column] = [value.strip() for value in values.split(VALUE_SEPARATOR) if value.strip()]
    return scope


# ═══════════════════════════════════════════════════════════════════════════════════
# APPLY THEM (step 7.2, predict_rows)
# ═══════════════════════════════════════════════════════════════════════════════════

def rows_of_the_lever(rows: pd.DataFrame, lever, configuration: Config) -> pd.Series:
    """The rows a lever applies to: its months and every column of its scope (compared as text; a number written
    1 or 1.0 is the same value)."""
    period = configuration.period_col
    inside = (rows[period] >= lever["_desde"]) & (rows[period] <= lever["_hasta"])
    for column, values in lever["_ambito"].items():
        if column not in rows.columns:
            return pd.Series(False, index=rows.index)
        as_text = rows[column].map(value_as_text)
        inside &= as_text.isin([value_as_text(value) for value in values])
    return inside


def value_as_text(value) -> str:
    """A value as the scope of a lever compares it: 1, 1.0 and '1' are '1'."""
    if isinstance(value, (bool, np.bool_)):
        return str(int(value))
    try:
        number = float(value)
        return str(int(number)) if number.is_integer() else str(number)
    except (TypeError, ValueError):
        return str(value).strip()


def apply_the_levers(rows: pd.DataFrame, levers: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """The rate and the uplift of the rows moved by every lever to apply, in the order of the file; the rate stays in
    [0, 1] and every band keeps its width around its value. Every row keeps what it had before (tasa_sin_palanca,
    uplift_sin_palanca) and the ids of the levers that moved it (palancas)."""
    rows = rows.copy()
    if RATE_BEFORE_LEVERS not in rows.columns:
        rows[RATE_BEFORE_LEVERS] = rows["tasa"]
        rows[UPLIFT_BEFORE_LEVERS] = rows["uplift"]
        rows[LEVERS_COLUMN] = ""
    if levers is None or levers.empty:
        return rows
    for _, lever in levers[levers["aplicar"]].iterrows():
        inside = rows_of_the_lever(rows, lever, configuration)
        if not inside.any():
            continue
        kind, value = lever["tipo"], float(lever["valor"])
        if kind.startswith("tasa"):
            before = rows.loc[inside, "tasa"]
            after = (before + value / 100.0 if kind == "tasa_suma_pp" else before * value).clip(0.0, 1.0)
            shift = after - before
            rows.loc[inside, "tasa"] = after
            rows.loc[inside, "tasa_baja"] = (rows.loc[inside, "tasa_baja"] + shift).clip(0.0, 1.0)
            rows.loc[inside, "tasa_alta"] = (rows.loc[inside, "tasa_alta"] + shift).clip(0.0, 1.0)
            rows.loc[inside, "tasa_baja"] = np.minimum(rows.loc[inside, "tasa_baja"], rows.loc[inside, "tasa"])
            rows.loc[inside, "tasa_alta"] = np.maximum(rows.loc[inside, "tasa_alta"], rows.loc[inside, "tasa"])
        else:
            before = rows.loc[inside, "uplift"]
            after = before * value if kind == "uplift_multiplica" else before + value
            shift = after - before
            rows.loc[inside, "uplift"] = after
            rows.loc[inside, "uplift_bajo"] = rows.loc[inside, "uplift_bajo"] + shift
            rows.loc[inside, "uplift_alto"] = rows.loc[inside, "uplift_alto"] + shift
        rows.loc[inside, LEVERS_COLUMN] = [f"{applied}{'+' if applied else ''}{lever['id']}"
                                           for applied in rows.loc[inside, LEVERS_COLUMN]]
    return rows


# ═══════════════════════════════════════════════════════════════════════════════════
# WHAT EVERY LEVER DID
# ═══════════════════════════════════════════════════════════════════════════════════

def levers_applied(future: pd.DataFrame, levers: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """One row per lever of the file: whether it was applied, the rows and the USD due it touched, and the direct
    effect of those rows by year (when two levers touch the same row, the row's effect counts in both)."""
    columns = ["id", "descripcion", "acordado_con", "fecha_acuerdo", "estado", "ambito", "desde", "hasta", "tipo", "valor",
               "aplicada", "filas", "vence_usd", "efecto_usd"]
    if levers is None or levers.empty:
        return pd.DataFrame(columns=columns)
    years = sorted(future[configuration.period_col].map(lambda month: month.year).unique())
    records = []
    for _, lever in levers.iterrows():
        touched = future[LEVERS_COLUMN].map(lambda applied: lever["id"] in str(applied).split("+")) if LEVERS_COLUMN in future else \
            pd.Series(False, index=future.index)
        record = {column: lever[column] for column in columns[:10]}
        record.update({"aplicada": bool(lever["aplicar"]) and bool(touched.any()), "filas": int(touched.sum()),
                       "vence_usd": float(future.loc[touched, DUE_USD_AT_DUE_COLUMN].sum()),
                       "efecto_usd": float(future.loc[touched, LEVER_EFFECT_COLUMN].sum())})
        for year in years:
            in_year = touched & (future[configuration.period_col].map(lambda month: month.year) == year)
            record[f"efecto_usd_{year}"] = float(future.loc[in_year, LEVER_EFFECT_COLUMN].sum())
        records.append(record)
    return pd.DataFrame(records)
