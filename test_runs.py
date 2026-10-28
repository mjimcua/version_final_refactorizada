"""
test_runs.py — The register of runs (runs.py): every forecast leaves its row and the picture of its result, appended;
the reference delivered to the business is frozen and can be read back.

A · a forecast is registered: its row (cut, kind, stages, forecast dynamic, totals = sff_resumen_negocio) and its
    picture (the money of the core from the current year on)
B · the register grows: a second run adds its row and its picture, the first one stays as it was
C · the reference: a run of kind referencia is frozen; an earlier run can be frozen by its id; the last one frozen is
    the reference, with its picture; an unknown run is refused
D · without an SQL engine the run is not registered, and it says so; the words of the command line set the kind
E · reality against the reference (report 9.2): a reference of one cut followed from the next one; the gap split into
    pipeline and yield adds up

    python test_runs.py
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import tempfile

import numpy as np
import pandas as pd

from config import TABLE_RUN_SNAPSHOT, TABLE_RUNS
from main import stages_of_the_command_line
from report_queries import table_in_sql
from runs import freeze_the_reference, register_the_run, the_reference
from stages import StagesToRun, run_stages
from test_helpers import check, check_stops, console_of, finish, synthetic_with


def register_of(configuration) -> pd.DataFrame:
    return pd.read_sql(f"SELECT * FROM {table_in_sql(configuration, TABLE_RUNS)}", configuration.sql_engine)


def picture_of(configuration) -> pd.DataFrame:
    return pd.read_sql(f"SELECT * FROM {table_in_sql(configuration, TABLE_RUN_SNAPSHOT)}", configuration.sql_engine)


def test_a_forecast_is_registered(configuration, first) -> None:
    print("A · a forecast is registered")
    register = register_of(configuration)
    row = register.iloc[0]
    summary = pd.read_sql("SELECT ano, total_usd FROM sff_resumen_negocio", configuration.sql_engine).set_index("ano")["total_usd"]
    current = configuration.calendar_boundaries()["current"]
    check(len(register) == 1 and row["corte"] == str(current) and row["tipo"] == "baseline"
          and row["maduracion_huella"] != "" and len(str(row["huella_codigo"])) == 12,
          f"its row: run {row['run_id']}, cut {row['corte']}, kind {row['tipo']}, "
          f"forecast dynamic {row['maduracion_huella']}, code {row['huella_codigo']}")
    check(np.isclose(row["anio_en_curso_total_usd"], summary.loc[current.year])
          and np.isclose(row["anio_siguiente_total_usd"], summary.loc[current.year + 1]),
          f"its totals are the ones of sff_resumen_negocio ({current.year} ${row['anio_en_curso_total_usd']:,.0f}, "
          f"{current.year + 1} ${row['anio_siguiente_total_usd']:,.0f})")
    core = pd.read_sql(f"SELECT SUM(COALESCE(forecast_renewed_USD, 0)) AS renovado, SUM(COALESCE(forecast_to_renew_USD, 0)) AS vence "
                       f"FROM sff_nucleo WHERE forecast_year >= {current.year}", configuration.sql_engine).iloc[0]
    picture = picture_of(configuration)
    check(np.isclose(picture["renovado_usd"].sum(), core["renovado"]) and np.isclose(picture["vence_usd"].sum(), core["vence"])
          and set(picture["run_id"]) == {row["run_id"]},
          f"its picture has the money of the core from {current.year} on ({len(picture):,} rows, "
          f"${picture['renovado_usd'].sum():,.0f} renewed)")


def test_the_register_grows(configuration, first) -> None:
    print("B · the register grows")
    before = picture_of(configuration)
    second = {}
    console_of(lambda: second.update(run_stages(configuration, StagesToRun(data=False, learning=False, kind="escenario",
                                                                          note="la misma con otros supuestos"))))
    register = register_of(configuration)
    after = picture_of(configuration)
    first_again = after[after["run_id"] == first["run"]["run_id"]].reset_index(drop=True)
    check(len(register) == 2 and list(register["tipo"]) == ["baseline", "escenario"]
          and register["nota"].iloc[1] == "la misma con otros supuestos",
          "a second run adds its row: baseline, then the escenario with its note")
    check(len(after) == 2 * len(before) and np.allclose(first_again["renovado_usd"], before["renovado_usd"]),
          "its picture is added; the one of the first run stays as it was")
    return second


def test_the_reference(configuration, first, second) -> None:
    print("C · the reference")
    delivered = {}
    console_of(lambda: delivered.update(run_stages(configuration, StagesToRun(data=False, learning=False, kind="referencia",
                                                                             note="entregada a negocio"))))
    reference, picture = the_reference(configuration)
    check(delivered.get("reference", {}).get("run_id") == delivered["run"]["run_id"] == reference["run_id"]
          and len(picture) > 0 and set(picture["run_id"]) == {reference["run_id"]},
          f"a run of kind referencia is frozen and is the reference of the cut, with its picture ({len(picture):,} rows)")
    console_of(lambda: freeze_the_reference(configuration, first["run"]["run_id"], "la primera, por error de entrega"))
    reference, _ = the_reference(configuration)
    check(reference["run_id"] == first["run"]["run_id"], "an earlier run frozen by its id: the last one frozen is the reference")
    check_stops(lambda: freeze_the_reference(configuration, "19990101-000000-000000"), "is not in the register",
                "an unknown run is refused")


def test_without_an_engine_and_the_words() -> None:
    print("D · without an engine; the words of the command line")
    without_engine = synthetic_with(sql_engine=None, output_folder=tempfile.mkdtemp())
    run = {}
    console = console_of(lambda: run.update(register_the_run(without_engine)))
    check(not run and "the run is not registered" in console, "without an SQL engine: not registered, and it says so")
    check(stages_of_the_command_line(["escenario"]).kind == "escenario" and stages_of_the_command_line(["referencia"]).kind == "referencia"
          and stages_of_the_command_line([]).kind == "baseline",
          "the words escenario and referencia set the kind; baseline by default")


def test_following_the_reference() -> None:
    print("E · reality against the reference (report 9.2): a reference of cut 2026-08, followed from cut 2026-09")
    from informe_forecast import gap_split, report
    august = synthetic_with(current_month="2026-08")
    console_of(lambda: run_stages(august, StagesToRun(kind="referencia", note="entregada en agosto")))
    september = synthetic_with(sql_engine=august.sql_engine, output_folder=august.output_folder)
    console_of(lambda: run_stages(september, StagesToRun()))
    answers = {}
    console = console_of(lambda: answers.update(report(september, ["9.2"], show=False)))
    table = answers["9.2"].table
    check(table is not None and set(table["mes"].astype(str)) == {"2026-08"} and len(answers["9.2"].charts) == 1,
          "9.2 compares the month closed since the reference (2026-08) and draws it")
    real = pd.read_sql("SELECT SUM(COALESCE(forecast_renewed_USD, 0)) AS renovado FROM sff_nucleo "
                       "WHERE forecast_status = 'actual' AND period = '2026-08'", september.sql_engine)["renovado"].iloc[0]
    reference, picture = the_reference(august)
    expected = picture[picture["mes"].astype(str) == "2026-08"]["renovado_usd"].sum()
    check(np.isclose(table["real_renovado_usd"].sum(), real) and np.isclose(table["ref_renovado_usd"].sum(), expected),
          f"real = the core of cut 2026-09 in 2026-08 (${real:,.0f}); expected = the picture of the reference (${expected:,.0f})")
    split = gap_split(table)
    check(np.allclose(split["efecto_pipeline"] + split["efecto_rendimiento"], split["diferencia"]),
          "pipeline effect + yield effect = the gap, row by row")
    check("RESPUESTA:" in console and "entregada en agosto" in console, "the answer names the reference and its note")
    unfollowed = synthetic_with()
    console_of(lambda: run_stages(unfollowed, StagesToRun()))
    none = {}
    console_of(lambda: none.update(report(unfollowed, ["9.2"], show=False)))
    check(none["9.2"].table is None, "without a reference of an earlier cut, 9.2 is not answered (and says why)")


if __name__ == "__main__":
    run_configuration = synthetic_with()
    first_run = {}
    console_of(lambda: first_run.update(run_stages(run_configuration, StagesToRun())))
    test_a_forecast_is_registered(run_configuration, first_run)
    second_run = test_the_register_grows(run_configuration, first_run)
    test_the_reference(run_configuration, first_run, second_run)
    test_without_an_engine_and_the_words()
    test_following_the_reference()
    finish()
