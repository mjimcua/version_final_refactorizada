"""
test_forecast_dynamics.py — Stage 2 (the forecast dynamics): the maturation of the customer states learned by step 4.1 is
persisted with its card; a run that reads it back gives the same forecast without examining the curve again; a card
that does not match the run stops it.

A · learning persists the dynamic: its card, the exam of the curve, the curve of the portfolio, by region
B · the forecast with the persisted dynamic = the forecast that learned it (by month, by year, the exam), and
    step 4.1 does not run (its curve is not examined again)
C · a curve rejected by its exam stays rejected when the dynamic is read back
D · the guards: no dynamic, another cut, a field of the Config step 4.1 reads, other closed months
E · the stages: learning = False reads the dynamic; the words sin_aprender and escenario

    python test_forecast_dynamics.py
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import numpy as np
import pandas as pd

from forecast_dynamics import maturation_fingerprint, resume_the_maturation
from block_1_preparation import PreparationBlock, read_plain_table
from config import (TABLE_STAGE_2_MATURATION_BY_REGION, TABLE_STAGE_2_MATURATION_CARD, TABLE_STAGE_2_MATURATION_CURVE,
                    TABLE_STAGE_2_MATURATION_EXAM)
from main import SyntheticConfig, stages_of_the_command_line
from pipeline import Orchestrator
from stages import StagesToRun, run_stages
from test_helpers import check, check_stops, console_of, finish, synthetic_with

MATURATION_MONTHS = 12
# when the softcancel of a unit was set, k months before due (k = 0 … 12): a fixed split, so the curve is learnable
SOFTCANCEL_SET_AT = {0: 0.35, 1: 0.2, 2: 0.15, 3: 0.1, 6: 0.1, 12: 0.1}
MONTH_MOVED = "2026-05"                     # D: a closed month of the window whose units move
REJECTING_MAXIMUM_PP = -1.0                 # C: no curve misses by −1 pp or less: every curve is rejected (the split above
                                            # is learned exactly, so even 0 pp would let it pass)


class DatedSoftcancelConfig(SyntheticConfig):
    """The synthetic extract with softcancel_month_0 … softcancel_month_12: the units of every softcancel row split by
    when the mark was set (only the part set by the current month is visible in a future month)."""
    def read_raw(self) -> pd.DataFrame:
        raw = super().read_raw()
        current = pd.Period(self.current_month, freq="M")
        months_ahead = np.array([max((pd.Period(text, freq="M") - current).n + 1, 0) for text in raw["period"].astype(str)])
        marked = raw["softcancel"].to_numpy() == 1
        units = raw["total_tr_units"].to_numpy(dtype=float)
        for k in range(MATURATION_MONTHS + 1):
            share = SOFTCANCEL_SET_AT.get(k, 0.0)
            visible = (k >= months_ahead) | (months_ahead == 0)
            raw[f"softcancel_month_{k}"] = np.where(marked, np.where(visible, units * share, 0.0), np.nan)
        return raw


class MovedHistoryConfig(DatedSoftcancelConfig):
    """D: the same extract with the units of one closed month of the window moved (another load of the history)."""
    def read_raw(self) -> pd.DataFrame:
        raw = super().read_raw()
        moved = raw["period"].astype(str) == MONTH_MOVED
        raw.loc[moved, "total_tr_units"] = raw.loc[moved, "total_tr_units"] + 1
        return raw


def dated_configuration(configuration_class=DatedSoftcancelConfig, **overrides):
    """A Config of the synthetic with the softcancel dated (another class: another read_raw)."""
    base = synthetic_with(**overrides)
    arguments = {name: getattr(base, name) for name in base.__dataclass_fields__}
    arguments["maturation_dims"] = ["softcancel"]
    arguments.update({name: value for name, value in overrides.items() if name in arguments})
    return configuration_class(**arguments)


def same_frame(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    try:
        pd.testing.assert_frame_equal(left, right, check_dtype=True)
        return True
    except AssertionError as difference:
        print(f"       {str(difference)[:300]}")
        return False


def card_of(configuration) -> dict:
    table = read_plain_table(TABLE_STAGE_2_MATURATION_CARD, configuration)
    return dict(zip(table["clave"].astype(str), table["valor"].astype(str)))


def fine_table_of(configuration) -> pd.DataFrame:
    block = PreparationBlock(configuration)
    console_of(block.run)
    return block.fine_table


def test_learning_persists_the_dynamic(learned) -> None:
    print("A · learning persists the dynamic")
    configuration, results, console = learned
    card = card_of(configuration)
    check(card["dinamica"] == "maduracion_estados" and card["corte"] == str(configuration.calendar_boundaries()["current"])
          and card["curvas_usadas"] == "softcancel" and card["estados_fechados"] == "softcancel",
          f"the card: cut {card['corte']}, learned as of {card['aprendido_a_fecha']}, curves used {card['curvas_usadas']}")
    exam = read_plain_table(TABLE_STAGE_2_MATURATION_EXAM, configuration)
    curve = read_plain_table(TABLE_STAGE_2_MATURATION_CURVE, configuration)
    by_region = read_plain_table(TABLE_STAGE_2_MATURATION_BY_REGION, configuration)
    box = results["state_maturation"]
    check(len(exam) == len(box.curve_exams["softcancel"]) and len(curve) == MATURATION_MONTHS + 1 and len(by_region) > 0,
          f"the exam of the curve ({len(exam)} horizons), the curve of the portfolio (k = 0 … {MATURATION_MONTHS}) and the "
          f"maturation by region ({len(by_region)} rows) are written")
    check("forecast dynamic 'maduracion_estados' persisted" in console, "the run says it persisted the dynamic")


def test_the_forecast_with_the_dynamic(learned) -> None:
    print("B · the forecast with the persisted dynamic = the forecast that learned it")
    configuration, results, _ = learned
    reading = dated_configuration(sql_engine=configuration.sql_engine)
    resumed = {}
    console = console_of(lambda: resumed.update(Orchestrator(reading).run(learn_dynamics=False)))
    check("STEP 4.1 · MATURATION" not in console and "softcancel: the exam of the curve in" not in console
          and "step 4.1 not run: its box comes from the forecast dynamic" in console,
          "step 4.1 does not run: the curve is not examined again, the box comes from the dynamic")
    check(same_frame(results["forecast"]["by_month"], resumed["forecast"]["by_month"])
          and same_frame(results["forecast"]["by_year"], resumed["forecast"]["by_year"]),
          f"the forecast by month and by year is the same (${results['forecast']['by_year']['total_usd'].sum():,.0f})")
    check(same_frame(results["series_exam"]["summary"], resumed["series_exam"]["summary"]),
          "the exam of step 7.1 (the honest one too) is the same")
    learned_exam, read_exam = results["state_maturation"].curve_exams, resumed["state_maturation"].curve_exams
    check(set(learned_exam) == set(read_exam)
          and np.allclose(learned_exam["softcancel"]["error_curva_abs_pp"], read_exam["softcancel"]["error_curva_abs_pp"])
          and learned_exam["softcancel"].attrs["passes"] == read_exam["softcancel"].attrs["passes"],
          "the exam of the curve and its decision come back with the box (the verdict and the report read them)")


def test_a_rejected_curve_stays_rejected() -> None:
    print("C · a curve rejected by its exam stays rejected")
    configuration = dated_configuration(maturation_curve_max_error_pp=REJECTING_MAXIMUM_PP)
    learned = {}
    console_of(lambda: learned.update(Orchestrator(configuration).run()))
    reading = dated_configuration(sql_engine=configuration.sql_engine, maturation_curve_max_error_pp=REJECTING_MAXIMUM_PP)
    resumed = {}
    console_of(lambda: resumed.update(Orchestrator(reading).run(learn_dynamics=False)))
    check(card_of(configuration)["curvas_rechazadas"] == "softcancel" and reading.rejected_maturation_dims == ["softcancel"]
          and not resumed["state_maturation"].curves,
          "with a maximum error of −1 pp the curve is rejected, and it stays rejected when the dynamic is read back")
    check(same_frame(learned["forecast"]["by_year"], resumed["forecast"]["by_year"]),
          "the forecast with the rejected curve is the same")


def test_the_guards() -> None:
    print("D · the guards of the card")
    empty = dated_configuration()
    fine_table = fine_table_of(empty)
    check_stops(lambda: resume_the_maturation(fine_table, empty), "run stage 2 first", "no dynamic: it stops and says what to do")
    configuration = dated_configuration()
    console_of(lambda: Orchestrator(configuration).run())
    fine_table = fine_table_of(configuration)
    other_support = dated_configuration(sql_engine=configuration.sql_engine,
                                        maturation_min_units=configuration.maturation_min_units + 1)
    check_stops(lambda: resume_the_maturation(fine_table_of(other_support), other_support), "config.maturation_min_units",
                "a field of the Config step 4.1 reads changed: it stops, naming it")
    other_cut = dated_configuration(sql_engine=configuration.sql_engine, current_month="2026-08")
    check_stops(lambda: resume_the_maturation(fine_table_of(other_cut), other_cut), "corte",
                "another cut: it stops, naming it")
    moved = dated_configuration(MovedHistoryConfig, sql_engine=configuration.sql_engine)
    check_stops(lambda: resume_the_maturation(fine_table_of(moved), moved), "historia_unidades",
                f"the closed months it learned from changed ({MONTH_MOVED}): it stops, naming it")
    same = dated_configuration(sql_engine=configuration.sql_engine)
    check(maturation_fingerprint(fine_table, configuration) == maturation_fingerprint(fine_table_of(same), same),
          "the same extract and Config: the same fingerprint")


def test_the_stages() -> None:
    print("E · the stages")
    configuration = dated_configuration()
    console_of(lambda: run_stages(configuration, StagesToRun(data=True, learning=True)))
    reading = dated_configuration(sql_engine=configuration.sql_engine)
    results = {}
    console = console_of(lambda: results.update(run_stages(reading, StagesToRun(data=False, learning=False))))
    check("forecast" in results and "the SQL of the pipeline is not run again" in console
          and "step 4.1 not run" in console,
          "a scenario of the month (no data, no learning): the persisted dataset and the persisted dynamic")
    check(stages_of_the_command_line(["sin_aprender"]).learning is False
          and stages_of_the_command_line(["escenario"]).data is False and stages_of_the_command_line(["escenario"]).learning is False,
          "the words of the command line: sin_aprender, escenario (= sin_datos + sin_aprender)")


if __name__ == "__main__":
    learning_configuration = dated_configuration()
    learned_results = {}
    learning_console = console_of(lambda: learned_results.update(Orchestrator(learning_configuration).run()))
    test_learning_persists_the_dynamic((learning_configuration, learned_results, learning_console))
    test_the_forecast_with_the_dynamic((learning_configuration, learned_results, learning_console))
    test_a_rejected_curve_stays_rejected()
    test_the_guards()
    test_the_stages()
    finish()
