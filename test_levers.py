"""
test_levers.py — The levers agreed with the business (levers.py): read and checked, applied in step 7.2 only, every row
with its rate and uplift before them and its direct effect; the scenario registered next to its baseline.

A · a lever on the rate: the rows of its scope and months take +pp (their band moves with it), the others do not; the
    direct effect of every row is expected − the row without the lever
B · a lever on the months of the simulation window also moves next year: what renews more falls due again
C · the exam of step 7.1 is the one without levers (the exam measures the method, not the campaign)
D · the file: only the levers of levers_states are applied; a lever that touches nothing is a warning; a file with
    problems stops, naming every one
E · the register: a run with levers is a scenario, with the ids it applied and its direct effect
F · a lever on the uplift: × valor on its scope

    python test_levers.py
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import os
import tempfile

import numpy as np
import pandas as pd

from config import DUE_USD_AT_DUE_COLUMN
from levers import LEVER_EFFECT_COLUMN, LEVER_COLUMNS, read_the_levers
from pipeline import Orchestrator
from stages import StagesToRun, run_stages
from test_helpers import check, check_stops, console_of, finish, synthetic_with

RATE_POINTS = 10.0                          # A: +10 pp in EU, September to December of next year (the months the synthetic has)
WINDOW_POINTS = 5.0                         # B: +5 pp in every row of the simulation window


def levers_file(rows: list) -> str:
    """A levers file with these rows (the columns of LEVER_COLUMNS), ; as separator."""
    path = os.path.join(tempfile.mkdtemp(), "palancas.csv")
    frame = pd.DataFrame(rows, columns=LEVER_COLUMNS)
    frame.to_csv(path, sep=";", index=False)
    return path


def lever(identifier, scope, since, until, kind, value, state="acordada"):
    return [identifier, f"prueba {identifier}", "test", "2026-10-28", state, scope, since, until, kind, value]


def run_with(path=None, **overrides) -> dict:
    configuration = synthetic_with(levers_file=path, **overrides)
    results = {}
    console = console_of(lambda: results.update(Orchestrator(configuration).run()))
    results["_console"] = console
    results["_configuration"] = configuration
    return results


def rows_of(results: dict) -> pd.DataFrame:
    forecast = results["forecast"]
    for key in ("forecast", "future"):
        if key in forecast:
            return forecast[key]
    raise KeyError(f"the forecast has no rows: {list(forecast)}")


def test_a_lever_on_the_rate(baseline, with_rate) -> None:
    print("A · a lever on the rate")
    rows = rows_of(with_rate)
    period = with_rate["_configuration"].period_col
    in_scope = (rows["region"].astype(str) == "EU") & (rows[period] >= pd.Period("2027-09", freq="M")) \
        & (rows[period] <= pd.Period("2027-12", freq="M"))
    moved = rows.loc[in_scope]
    expected = (moved["tasa_sin_palanca"] + RATE_POINTS / 100).clip(0, 1)
    check(in_scope.any() and np.allclose(moved["tasa"], expected) and (moved["palancas"] == "P-A").all(),
          f"the {int(in_scope.sum())} rows of EU in 2027-09..2027-12 take +{RATE_POINTS:g} pp and carry the id of the lever")
    outside = rows.loc[~in_scope]
    check(np.allclose(outside["tasa"], outside["tasa_sin_palanca"]) and (outside["palancas"] == "").all()
          and np.allclose(outside[LEVER_EFFECT_COLUMN], 0),
          "the other rows keep their rate, carry no lever and no effect")
    check((moved["tasa_baja"] <= moved["tasa"] + 1e-12).all() and (moved["tasa"] <= moved["tasa_alta"] + 1e-12).all(),
          "the band moves with the rate (low ≤ rate ≤ high)")
    direct = moved["esperado_usd"] - moved[DUE_USD_AT_DUE_COLUMN] * moved["tasa_sin_palanca"] * moved["uplift_sin_palanca"]
    check(np.allclose(moved[LEVER_EFFECT_COLUMN], direct) and moved[LEVER_EFFECT_COLUMN].sum() > 0,
          f"the direct effect of every row = expected − the row without the lever (${moved[LEVER_EFFECT_COLUMN].sum():,.0f})")
    by_year_base = baseline["forecast"]["by_year"].set_index("ano")["total_usd"]
    by_year_lever = with_rate["forecast"]["by_year"].set_index("ano")["total_usd"]
    check(np.isclose(by_year_lever.loc[2027] - by_year_base.loc[2027], moved[LEVER_EFFECT_COLUMN].sum())
          and np.isclose(by_year_lever.loc[2026], by_year_base.loc[2026]),
          "the total of 2027 grows by the direct effect; 2026 does not move")


def test_a_lever_on_the_window(baseline, with_window) -> None:
    print("B · a lever on the simulation window moves next year")
    base = baseline["forecast"]["by_year"].set_index("ano")
    lever_year = with_window["forecast"]["by_year"].set_index("ano")
    rows = rows_of(with_window)
    effect_2026 = rows.loc[rows[with_window["_configuration"].period_col].map(lambda month: month.year) == 2026,
                           LEVER_EFFECT_COLUMN].sum()
    check(np.isclose(lever_year.loc[2026, "total_usd"] - base.loc[2026, "total_usd"], effect_2026) and effect_2026 > 0,
          f"2026 grows by the direct effect of the window (${effect_2026:,.0f})")
    check(lever_year.loc[2027, "esperado_proyectada_usd"] > base.loc[2027, "esperado_proyectada_usd"],
          f"what renews more in the window falls due again: the projected renewals of 2027 grow "
          f"(${base.loc[2027, 'esperado_proyectada_usd']:,.0f} → ${lever_year.loc[2027, 'esperado_proyectada_usd']:,.0f})")


def test_the_exam_has_no_levers(baseline, with_rate) -> None:
    print("C · the exam of step 7.1 is the one without levers")
    pd.testing.assert_frame_equal(baseline["series_exam"]["summary"], with_rate["series_exam"]["summary"])
    check(True, "the exam of every series and of the total is the same with and without levers")


def test_the_file() -> None:
    print("D · the file")
    path = levers_file([lever("P-ON", "region=EU", "2027-09", "2027-12", "tasa_suma_pp", "5"),
                        lever("P-OFF", "region=NA", "2027-09", "2027-12", "tasa_suma_pp", "5", state="propuesta"),
                        lever("P-NONE", "region=ASIA", "2027-09", "2027-12", "tasa_suma_pp", "5")])
    results = run_with(path)
    rows = rows_of(results)
    applied = set("+".join(rows["palancas"]).split("+")) - {""}
    check(applied == {"P-ON"}, f"only the levers acordada are applied (applied: {sorted(applied)})")
    check("WARN  every lever to apply touches some future row" in results["_console"] and "P-NONE" in results["_console"],
          "a lever whose scope matches nothing is a warning, with its id")
    table = pd.read_sql("SELECT * FROM sff_palancas_aplicadas", results["_configuration"].sql_engine)
    check(set(table["id"]) == {"P-ON", "P-OFF", "P-NONE"} and int(table.loc[table["id"] == "P-ON", "filas"].iloc[0]) > 0,
          "sff_palancas_aplicadas has every lever of the file, with the rows it touched")
    bad = levers_file([lever("P-1", "region=EU", "2027-13", "2027-03", "tasa_doble", "x"),
                       lever("P-1", "region", "2027-09", "2027-12", "tasa_suma_pp", "1")])
    check_stops(lambda: read_the_levers(synthetic_with(levers_file=bad)), "problems",
                "a file with a bad month, an unknown type, a value that is no number, a repeated id and a scope without "
                "value stops, naming every problem")
    message = ""
    try:
        read_the_levers(synthetic_with(levers_file=bad))
    except ValueError as error:
        message = str(error)
    check(all(text in message for text in ("2027-13", "tasa_doble", "'x'", "repeated ids", "ambito 'region'")),
          "every problem is named at once")


def test_the_register() -> None:
    print("E · the register: a run with levers is a scenario")
    path = levers_file([lever("P-REG", "region=EU", "2027-09", "2027-12", "tasa_suma_pp", "2")])
    configuration = synthetic_with(levers_file=path)
    results = {}
    console = console_of(lambda: results.update(run_stages(configuration, StagesToRun(kind="baseline", note="campaña EU"))))
    run = results["run"]
    check(run["tipo"] == "escenario" and run["palancas"] == "P-REG" and run["palancas_efecto_directo_usd"] > 0
          and "registered as an escenario" in console,
          f"registered as an escenario (not a baseline), with its levers and its direct effect "
          f"(${run['palancas_efecto_directo_usd']:,.0f})")


def test_a_lever_on_the_uplift() -> None:
    print("F · a lever on the uplift")
    path = levers_file([lever("P-UP", "product=A", "2026-10", "2027-12", "uplift_multiplica", "1.1")])
    results = run_with(path)
    rows = rows_of(results)
    in_scope = (rows["product"].astype(str) == "A") & (rows[results["_configuration"].period_col] >= pd.Period("2026-10", freq="M"))
    check(np.allclose(rows.loc[in_scope, "uplift"], rows.loc[in_scope, "uplift_sin_palanca"] * 1.1)
          and np.allclose(rows.loc[~in_scope, "uplift"], rows.loc[~in_scope, "uplift_sin_palanca"]),
          "the rows of product A from 2026-10 take the uplift × 1.1, the others keep theirs")


if __name__ == "__main__":
    baseline_results = run_with()
    rate_results = run_with(levers_file([lever("P-A", "region=EU", "2027-09", "2027-12", "tasa_suma_pp", str(RATE_POINTS))]))
    window_results = run_with(levers_file([lever("P-W", "", "2026-10", "2026-12", "tasa_suma_pp", str(WINDOW_POINTS))]))
    test_a_lever_on_the_rate(baseline_results, rate_results)
    test_a_lever_on_the_window(baseline_results, window_results)
    test_the_exam_has_no_levers(baseline_results, rate_results)
    test_the_file()
    test_the_register()
    test_a_lever_on_the_uplift()
    finish()
