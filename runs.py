"""
runs.py — THE RUNS: every forecast registered with its cut, its inputs and a picture of its result, and the reference
delivered to the business frozen, so reality can be followed against it (28-oct-2026, PLAN_etapas.md, milestone H5).

MISSION: a forecast is a number given on a date with some inputs. To follow it (stage 5, monitoring), every run leaves
a row that says what it was (cut, kind, note, the forecast dynamics it used, its total) and a PICTURE of its
result at the grain the business reads it (month × region × product × term × origin). The tables of a run (sff_nucleo,
sff_forecast_mes…) are replaced by the next run; these are not: they only grow, one run after another.

THE KINDS OF RUN (RUN_KIND in main.py, or the words of the command line):
  baseline     the forecast as the framework makes it (the default)
  escenario    a scenario: the same cut with other inputs (python main.py escenario: no SQL, no learning)
  referencia   the forecast delivered to the business: registered and FROZEN (python main.py referencia). A frozen run
               cannot be changed: it is a row in sff_ejecucion_referencias that points at its run, and its picture is
               the one written when it ran. Any earlier run can be frozen too: freeze_the_reference(configuration, run_id).

WHAT IT WRITES (appended, never replaced; with table_prefix):
  ejecuciones              one row per run: run_id, cut, kind, note, when, the stages it ran,
                           the forecast dynamic of the maturation (its fingerprint), the fingerprint of the code, the total of
                           the current year and of the next one with the band of the exam, the seconds
  ejecucion_foto           per run: month × the dims of run_snapshot_dims × universe × pipeline source × status: units and
                           USD due, units and USD renewed (real in the closed months, expected in the future), from the
                           current year to the next December
  ejecucion_referencias    one row per frozen reference: run_id, cut, when it was frozen, its note

THE INTERFACE:
  run = register_the_run(configuration, kind, note, stages_text, seconds)   after the forecast (stages.py calls it)
  freeze_the_reference(configuration, run_id=None, note="")                 None: the last run of this cut
  the_reference(configuration)                                               the last frozen run of this cut and its picture
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import datetime
import glob
import hashlib
import os
import time

import pandas as pd
from sqlalchemy import inspect
from sqlalchemy import text as text_of

from config import (TABLE_BUSINESS_SUMMARY, TABLE_CORE, TABLE_LEVERS_APPLIED, TABLE_RUN_REFERENCES, TABLE_RUN_SNAPSHOT,
                    TABLE_RUNS, TABLE_STAGE_2_MATURATION_CARD, Config)
from report_queries import table_in_sql, year_by_region_columns

# ─── named constants ─────────────────────────────────────────────────────────────
RUNS_LABEL = "E5"
RUN_KINDS = ("baseline", "escenario", "referencia")
RUN_ID_FORMAT = "%Y%m%d-%H%M%S-%f"        # to the microsecond: two runs never share an id
CODE_FILES = "*.py"                       # the fingerprint of the code: every module of the framework next to this one


# ═══════════════════════════════════════════════════════════════════════════════════
# REGISTER A RUN
# ═══════════════════════════════════════════════════════════════════════════════════

def register_the_run(configuration: Config, kind: str = "baseline", note: str = "", stages_text: str = "",
                     seconds: float = 0.0) -> dict:
    """One row in sff_ejecuciones and the picture of the result in sff_ejecucion_foto, appended. Needs the tables of
    the run in SQL (without an engine, nothing is registered and it says so). Returns the row."""
    if kind not in RUN_KINDS:
        raise ValueError(f"the kind of run must be one of {RUN_KINDS} (found '{kind}')")
    logger = configuration.logger
    if configuration.sql_engine is None:
        logger.warning(f"[{RUNS_LABEL}] the run is not registered: the register of runs lives in SQL (no sql_engine)")
        return {}
    started = time.time()
    boundaries = configuration.calendar_boundaries()
    current_year = boundaries["current"].year
    run = {"run_id": datetime.datetime.now().strftime(RUN_ID_FORMAT), "corte": str(boundaries["current"]),
           "tipo": kind, "nota": note, "escrito": datetime.datetime.now().isoformat(timespec="seconds"),
           "etapas": stages_text, "huella_codigo": code_fingerprint(), "segundos": round(float(seconds), 1)}
    run.update(card_values(configuration, TABLE_STAGE_2_MATURATION_CARD, {"escrito": "maduracion_escrito",
                                                                          "huella": "maduracion_huella"}))
    run.update(levers_of_the_run(configuration))
    if run["palancas"] and kind == "baseline":
        # a baseline is the forecast of the method: a run with levers is a scenario
        logger.warning(f"[{RUNS_LABEL}] the run applied the levers {run['palancas']}: registered as an escenario, not "
                       f"as a baseline (RUN_KIND)")
        run["tipo"] = kind = "escenario"
    summary = business_summary(configuration)
    for name, year in (("anio_en_curso", current_year), ("anio_siguiente", current_year + 1)):
        of_year = summary[summary["ano"] == year]
        run[name] = year
        for column in ("total_usd", "banda_examen_baja", "banda_examen_alta"):
            run[f"{name}_{column}"] = float(of_year[column].iloc[0]) if len(of_year) and column in of_year else float("nan")
    snapshot = the_picture(configuration).assign(run_id=run["run_id"])
    append_rows(pd.DataFrame([run]), TABLE_RUNS, configuration)
    append_rows(snapshot, TABLE_RUN_SNAPSHOT, configuration)
    logger.doc(f"[{RUNS_LABEL}] run {run['run_id']} registered ({kind}{': ' + note if note else ''}) in "
               f"{configuration.table_prefix}{TABLE_RUNS}, its picture in {configuration.table_prefix}{TABLE_RUN_SNAPSHOT} "
               f"({len(snapshot):,} rows) · {current_year} ${run['anio_en_curso_total_usd'] or 0:,.0f} · "
               f"{current_year + 1} ${run['anio_siguiente_total_usd'] or 0:,.0f} · {time.time() - started:.1f}s")
    return run


def the_picture(configuration: Config) -> pd.DataFrame:
    """The result of the run at the grain the business reads it, from the core: month × run_snapshot_dims × universe ×
    pipeline source × status, from the current year to the next December."""
    core = table_in_sql(configuration, TABLE_CORE)
    dims = snapshot_dims(configuration)
    dim_list = "".join(f"n.{dim}, " for dim in dims)
    query = f"""SELECT n.{configuration.period_col} AS mes, {dim_list}n.forecast_universe AS universo,
       n.forecast_pipeline_source AS origen, n.forecast_status AS estado,
       SUM(COALESCE(n.forecast_to_renew_units, 0)) AS vencen_unidades,
       SUM(COALESCE(n.forecast_to_renew_USD, 0)) AS vence_usd,
       SUM(COALESCE(n.forecast_renewed_units, 0)) AS renovadas_unidades,
       SUM(COALESCE(n.forecast_renewed_USD, 0)) AS renovado_usd
FROM {core} n
WHERE n.forecast_year >= {configuration.calendar_boundaries()['current'].year}
GROUP BY n.{configuration.period_col}, {dim_list}n.forecast_universe, n.forecast_pipeline_source, n.forecast_status"""
    picture = pd.read_sql(query, configuration.sql_engine)
    for dim in dims:                       # the dims as text: the picture of every run has the same columns
        picture[dim] = picture[dim].astype(str)
    return picture


def snapshot_dims(configuration: Config) -> list:
    """The dims of the picture: run_snapshot_dims, or the two region levels and the term."""
    if configuration.run_snapshot_dims:
        return list(configuration.run_snapshot_dims)
    return year_by_region_columns(configuration) + ([configuration.term_column] if configuration.term_column else [])


def levers_of_the_run(configuration: Config) -> dict:
    """The levers this run applied (sff_palancas_aplicadas, written by step 7.2) and their direct effect."""
    if not table_exists(configuration, TABLE_LEVERS_APPLIED):
        return {"palancas": "", "palancas_efecto_directo_usd": 0.0}
    table = pd.read_sql(f"SELECT * FROM {table_in_sql(configuration, TABLE_LEVERS_APPLIED)}", configuration.sql_engine)
    if table.empty:
        return {"palancas": "", "palancas_efecto_directo_usd": 0.0}
    applied = table[table["aplicada"].astype(str).isin(["1", "True", "true"])]
    return {"palancas": "+".join(applied["id"].astype(str)),
            "palancas_efecto_directo_usd": float(pd.to_numeric(applied["efecto_usd"]).sum())}


def business_summary(configuration: Config) -> pd.DataFrame:
    """sff_resumen_negocio of the run (written by step 7.2): the total of every year and its band."""
    return pd.read_sql(f"SELECT * FROM {table_in_sql(configuration, TABLE_BUSINESS_SUMMARY)}", configuration.sql_engine)


def card_values(configuration: Config, card_table: str, keys: dict) -> dict:
    """Some values of a card (stage 2) under the names of the register; empty when there is no card."""
    try:
        card = pd.read_sql(f"SELECT * FROM {table_in_sql(configuration, card_table)}", configuration.sql_engine)
    except Exception:
        return {name: "" for name in keys.values()}
    values = dict(zip(card["clave"].astype(str), card["valor"].astype(str)))
    return {name: values.get(key, "") for key, name in keys.items()}


def code_fingerprint() -> str:
    """The first 12 characters of the SHA-256 of every module of the framework: two runs with the same fingerprint ran
    the same code."""
    digest = hashlib.sha256()
    folder = os.path.dirname(os.path.abspath(__file__))
    for path in sorted(glob.glob(os.path.join(folder, CODE_FILES))):
        if os.path.basename(path).startswith("test_") or os.path.basename(path) == "entorno_local.py":
            continue
        with open(path, "rb") as handle:
            digest.update(handle.read())
    return digest.hexdigest()[:12]


def append_rows(frame: pd.DataFrame, table_name: str, configuration: Config) -> None:
    """The rows added at the end of a table of the register (created the first time); never replaced. A column a newer
    version of the register brings is added to the table first (the rows written before have it empty)."""
    physical_name = f"{configuration.table_prefix}{table_name}"
    if table_exists(configuration, table_name):
        existing = {column["name"] for column in inspect(configuration.sql_engine).get_columns(
            physical_name, schema=configuration.sql_schema)}
        qualified_name = table_in_sql(configuration, table_name)
        with configuration.sql_engine.begin() as connection:
            for column in [column for column in frame.columns if column not in existing]:
                sql_type = "FLOAT" if pd.api.types.is_numeric_dtype(frame[column]) else "VARCHAR(4000)"
                connection.execute(text_of(f"ALTER TABLE {qualified_name} ADD {column} {sql_type}"))
    frame.to_sql(physical_name, configuration.sql_engine, schema=configuration.sql_schema, if_exists="append", index=False)


def table_exists(configuration: Config, table_name: str) -> bool:
    return (f"{configuration.table_prefix}{table_name}"
            in inspect(configuration.sql_engine).get_table_names(schema=configuration.sql_schema))


# ═══════════════════════════════════════════════════════════════════════════════════
# THE REFERENCE DELIVERED TO THE BUSINESS
# ═══════════════════════════════════════════════════════════════════════════════════

def freeze_the_reference(configuration: Config, run_id: str = None, note: str = "") -> dict:
    """Freeze a registered run as the reference delivered to the business (None: the last run of this cut). It is
    appended to sff_ejecucion_referencias; the run and its picture stay as they were written."""
    if configuration.sql_engine is None or not table_exists(configuration, TABLE_RUNS):
        raise ValueError("there is no register of runs to freeze from (sff_ejecuciones): run the forecast first")
    runs = pd.read_sql(f"SELECT run_id, corte, tipo, nota FROM {table_in_sql(configuration, TABLE_RUNS)}",
                       configuration.sql_engine)
    cut = str(configuration.calendar_boundaries()["current"])
    if run_id is None:
        of_cut = runs[runs["corte"].astype(str) == cut]
        if of_cut.empty:
            raise ValueError(f"no run of cut {cut} in the register: nothing to freeze")
        run_id = str(of_cut["run_id"].astype(str).max())
    chosen = runs[runs["run_id"].astype(str) == str(run_id)]
    if chosen.empty:
        raise ValueError(f"run {run_id} is not in the register (sff_ejecuciones)")
    reference = {"run_id": str(run_id), "corte": str(chosen["corte"].iloc[0]),
                 "congelada": datetime.datetime.now().isoformat(timespec="microseconds"), "nota": note}
    append_rows(pd.DataFrame([reference]), TABLE_RUN_REFERENCES, configuration)
    configuration.logger.doc(f"[{RUNS_LABEL}] run {run_id} frozen as the reference of cut {reference['corte']}"
                             + (f": {note}" if note else ""))
    return reference


def the_reference(configuration: Config) -> tuple:
    """(the last reference frozen for this cut, its picture); (None, None) when there is none."""
    if configuration.sql_engine is None or not table_exists(configuration, TABLE_RUN_REFERENCES):
        return None, None
    references = pd.read_sql(f"SELECT * FROM {table_in_sql(configuration, TABLE_RUN_REFERENCES)}", configuration.sql_engine)
    of_cut = references[references["corte"].astype(str) == str(configuration.calendar_boundaries()["current"])]
    if of_cut.empty:
        return None, None
    reference = of_cut.sort_values("congelada").iloc[-1].to_dict()
    picture = pd.read_sql(f"SELECT * FROM {table_in_sql(configuration, TABLE_RUN_SNAPSHOT)} "
                          f"WHERE run_id = '{reference['run_id']}'", configuration.sql_engine)
    return reference, picture
