"""
test_stage_1_analysis.py — Stage 1 (the analysis of the pipeline): the tables add up to the raw, the trend of a series
is read right, the month-against-month effects add up, the early states and the horizon are consistent, the
acquisition is read on observable months only, and the stage runs inside main with its words.

A · the pipeline by month and by year adds up to the raw; closed, future and complete months
B · the trend of a monthly series: rising, flat, seasonal, too short
C · the last closed month against the same month a year before: the three effects add up, by every dimension
D · the dated states (a synthetic with softcancel_month_0…12): the early share and the same horizon a year ago
E · the like-real extract: terms, acquisition on observable months, price increases, composition on the same months
F · the stages: data + analysis writes the tables and the markdown; the words sin_analisis, solo_analisis, escenario

    python test_stage_1_analysis.py
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import os
import tempfile

import numpy as np
import pandas as pd
from sqlalchemy import create_engine

import main
from block_1_preparation import read_plain_table
from main import stages_of_the_command_line
from stage_1_analysis import (CLOSED, FUTURE, LAST_12_MONTHS, LAST_MONTH, MONTHS_PER_YEAR, RISING, STABLE, TOO_SHORT, TOTAL,
                              acquisition_by_month, analyse_the_pipeline, composition_by_year, early_states,
                              month_against_month, pipeline_by_month, pipeline_by_year, pipeline_rows_of, states_at_horizon,
                              trend_of)
from stages import StagesToRun, run_stages
from test_forecast_dynamics import dated_configuration
from test_helpers import check, console_of, finish, synthetic_with


def like_real_in_a_temporary_folder():
    """The like-real Config (terms, acquisition by net_new, price groups, the softcancel dated) with its own SQLite
    file and output folder, so the test touches nothing of the other runs."""
    folder = tempfile.mkdtemp()
    configuration = main.like_real_configuration("2026-10")
    arguments = {name: getattr(configuration, name) for name in configuration.__dataclass_fields__}
    arguments.update(sql_engine=create_engine(f"sqlite:///{os.path.join(folder, 'parecido.db')}"), output_folder=folder,
                     levels_path=os.path.join(folder, "levels.json"), log_colors=False)
    return type(configuration)(**arguments)


def test_the_pipeline_adds_up() -> None:
    print("A · the pipeline by month and by year adds up to the raw")
    configuration = synthetic_with()
    raw = configuration.read_raw()
    rows, time_series_rows = pipeline_rows_of(raw, configuration)
    monthly = pipeline_by_month(rows, configuration)
    yearly = pipeline_by_year(monthly, configuration)
    not_time_series = raw[raw[configuration.flag_time_series_col] != 1]
    check(np.isclose(monthly["vence_usd"].sum(), not_time_series[configuration.pipeline_usd_col].sum())
          and np.isclose(monthly["vencen_unidades"].sum(), not_time_series[configuration.pipeline_units_col].sum()),
          f"the USD and the units due of every month add up to the raw of the renewal universe (${monthly['vence_usd'].sum():,.0f})")
    current = configuration.calendar_boundaries()["current"]
    closed = not_time_series[pd.PeriodIndex(not_time_series[configuration.period_col].astype(str), freq="M") < current]
    check(np.isclose(monthly["renovado_usd"].sum(), closed[configuration.renewed_usd_col].sum())
          and monthly.loc[monthly["estado"] == FUTURE, "renovado_usd"].isna().all(),
          "the renewed USD adds up to the closed months of the raw, and a future month has no renewed")
    months = pd.PeriodIndex(monthly["mes"], freq="M")
    check((monthly["estado"] == np.where(months < current, CLOSED, FUTURE)).all()
          and (monthly["completa"] == (months < current + MONTHS_PER_YEAR).astype(int)).all(),
          f"closed before {current}; complete up to {current + MONTHS_PER_YEAR - 1} (its 1-year licences already sold or renewed)")
    this_year = yearly[yearly["anio"] == current.year].iloc[0]
    same_months = monthly[(monthly["anio"] == current.year) & (monthly["completa"] == 1)]
    expected_growth = same_months["vence_usd"].sum() / same_months["vence_usd_ano_anterior"].sum() - 1
    check(np.isclose(this_year["crecimiento_usd_vs_ano_anterior"], expected_growth) and this_year["estado"] == "en_curso"
          and int(this_year["meses_comparables"]) == len(same_months),
          f"the growth of the current year is read on its comparable months against the same months a year before ({expected_growth:+.1%})")
    first_year = yearly.iloc[0]
    check(not np.isfinite(first_year["crecimiento_usd_vs_ano_anterior"]) and int(first_year["meses_comparables"]) == 0,
          "the first year of the extract has nothing to compare with")


def test_the_trend() -> None:
    print("B · the trend of a monthly series")
    configuration = synthetic_with()
    months = pd.period_range("2023-01", "2026-06", freq="M")
    time_in_years = np.arange(len(months)) / MONTHS_PER_YEAR
    rising = pd.Series(100.0 * (1 + 0.10 * time_in_years), index=months)
    trend = trend_of(rising, configuration)
    check(trend["tendencia"] == RISING and abs(trend["pendiente_anual"] - 10.0) < 1e-6 and trend["p_valor_tendencia"] < 1e-6
          and trend["estacional"] == 0,
          f"a series rising 10 a year is 'sube' with that slope ({trend['pendiente_anual']:.2f}) and no season")
    flat = pd.Series(100.0, index=months)
    trend = trend_of(flat, configuration)
    check(trend["tendencia"] == STABLE and trend["estacional"] == 0 and trend["p_valor_tendencia"] == 1.0,
          "a constant series is 'estable' and has no season (rounding is not a pattern)")
    seasonal = pd.Series(100.0 + 20.0 * np.sin(2 * np.pi * (months.month - 1) / MONTHS_PER_YEAR), index=months)
    trend = trend_of(seasonal, configuration)
    check(trend["estacional"] == 1 and "4" in trend["meses_alto"].split(",") and "10" in trend["meses_bajo"].split(",")
          and abs(trend["amplitud_estacional"] - 0.4) < 0.02,
          f"a seasonal series has a month effect: high in April, low in October, amplitude {trend['amplitud_estacional']:.0%} of the mean")
    short = pd.Series(100.0, index=months[:6])
    check(trend_of(short, configuration)["tendencia"] == TOO_SHORT, "fewer months than analysis_trend_min_months: no trend measured")
    shares = pd.Series(0.10 + 0.02 * time_in_years, index=months)
    trend = trend_of(shares, configuration, in_points=True)
    check(trend["tendencia"] == RISING and abs(trend["pendiente_anual"] - 2.0) < 1e-6,
          "a share rising 2 points a year: the slope in points")


def test_month_against_month() -> None:
    print("C · the last closed month against the same month a year before")
    configuration = synthetic_with()
    rows, _ = pipeline_rows_of(configuration.read_raw(), configuration)
    comparison = month_against_month(rows, configuration)
    effects = comparison["efecto_pipeline_usd"] + comparison["efecto_tasa_usd"] + comparison["efecto_uplift_usd"]
    check(np.allclose(effects, comparison["renovado_usd_diferencia"]),
          f"the three effects add up to the change of the renewed USD in every row ({len(comparison)} rows)")
    last_closed = rows.loc[rows["_cerrado"], "_mes"].max()
    total = comparison[(comparison["comparacion"] == LAST_MONTH) & (comparison["dimension"] == TOTAL)].iloc[0]
    now = rows[rows["_mes"] == last_closed]
    before = rows[rows["_mes"] == last_closed - MONTHS_PER_YEAR]
    check(total["mes_hoy"] == str(last_closed) and np.isclose(total["renovado_usd_hoy"], now[configuration.renewed_usd_col].sum())
          and np.isclose(total["renovado_usd_antes"], before[configuration.renewed_usd_col].sum())
          and np.isclose(total["vence_usd_hoy"], now[configuration.pipeline_usd_col].sum()),
          f"the total row is the last closed month ({last_closed}) against {last_closed - MONTHS_PER_YEAR}, as the raw sums them")
    for dimension, of_dimension in comparison[comparison["comparacion"] == LAST_MONTH].groupby("dimension"):
        if dimension == TOTAL:
            continue
        check(np.isclose(of_dimension["renovado_usd_hoy"].sum(), total["renovado_usd_hoy"])
              and np.isclose(of_dimension["efecto_pipeline_usd"].sum() + of_dimension["efecto_tasa_usd"].sum()
                             + of_dimension["efecto_uplift_usd"].sum(), total["renovado_usd_diferencia"]),
              f"the values of {dimension} add up to the total, in the money and in the effects")
    twelve = comparison[(comparison["comparacion"] == LAST_12_MONTHS) & (comparison["dimension"] == TOTAL)]
    check(len(twelve) == 1 and twelve.iloc[0]["mes_hoy"] == f"{last_closed - 11}..{last_closed}",
          "the last 12 closed months against the 12 before are compared too")


def test_the_dated_states() -> None:
    print("D · the dated states: the early share and the same horizon a year ago")
    configuration = dated_configuration()
    rows, _ = pipeline_rows_of(configuration.read_raw(), configuration)
    early = early_states(rows, configuration)
    current = configuration.calendar_boundaries()["current"]
    closed = early[early["estado_mes"] == CLOSED]
    check(len(early) and (closed["parte_primer_mes"] <= closed["parte_dos_primeros_meses"] + 1e-12).all()
          and (closed["parte_dos_primeros_meses"] <= closed["parte_final"] + 1e-12).all(),
          f"in every closed cohort: first month ≤ two first months ≤ final share ({len(closed)} months)")
    months = pd.PeriodIndex(early["mes"], freq="M")
    listed_up_to = min(current + configuration.maturation_months - 1, rows["_mes"].max())
    check(months.max() == listed_up_to and early["parte_primer_mes"].notna().all(),
          f"the early share is listed up to {listed_up_to}: the first month of every cohort is already seen")
    horizon = states_at_horizon(rows, configuration)
    check(len(horizon) and (horizon["horizonte_meses"] == (pd.PeriodIndex(horizon["mes"], freq="M") - (current - 1)).map(lambda offset: offset.n)).all()
          and horizon["horizonte_meses"].max() <= configuration.maturation_months
          and (horizon["parte_visible_hoy"] <= horizon["parte_final_ano_anterior"] + 0.05).all(),
          "every future month within the maturation months: its horizon, what is visible today, and the cohort of a year ago")


def test_the_like_real_extract() -> None:
    print("E · the like-real extract: terms, acquisition, price increases, composition")
    configuration = like_real_in_a_temporary_folder()
    raw = configuration.read_raw()
    rows, _ = pipeline_rows_of(raw, configuration)
    current = configuration.calendar_boundaries()["current"]
    acquisition = acquisition_by_month(rows, configuration)
    last_month = rows["_mes"].max()
    two_years = acquisition[acquisition["plazo_anios"] == 2]
    late = two_years[pd.PeriodIndex(two_years["mes_venta"], freq="M") > last_month - 2 * MONTHS_PER_YEAR]
    check(len(late) and (late["observable"] == 0).all() and late["vendidas_unidades"].isna().all(),
          "a 2-year acquisition sold less than 24 months before the end of the extract is not observable: no value")
    one_year = acquisition[(acquisition["plazo_anios"] == 1) & (acquisition["observable"] == 1)]
    sold = rows[rows["_adquisicion"] & (rows["_plazo_anios"] == 1)]
    sold_by_month = sold.groupby(sold["_mes"] - MONTHS_PER_YEAR)[configuration.pipeline_units_col].sum()
    check(np.isclose(one_year["vendidas_unidades"].sum(), sold_by_month[sold_by_month.index < current].sum())
          and pd.PeriodIndex(one_year["mes_venta"], freq="M").max() == current - 1,
          "the 1-year acquisitions by month of sale are the units due 12 months later, up to the last closed month of sale")
    composition, change = composition_by_year(rows, configuration)
    shares = composition.groupby(["dimension", "anio"])["parte_usd"].sum()
    check(np.allclose(shares, 1.0) and change["cambio_composicion"].between(0, 1).all(),
          "the shares of every dimension add up to 1 in every year; the change of the composition is in [0, 1]")
    next_year = change[change["anio"] == current.year + 1].iloc[0]
    check(next_year["meses"] == f"{current.year + 1}-01..{current + MONTHS_PER_YEAR - 1}"
          and next_year["meses_ano_anterior"] == f"{current.year}-01..{current - 1}",
          f"the next year is compared on its complete months against the same months of this year ({next_year['meses']} vs {next_year['meses_ano_anterior']})")
    analysis = {}
    console = console_of(lambda: analysis.update(analyse_the_pipeline(raw, configuration)))
    tables = analysis["tables"]
    increases = tables["subidas_precio"]
    check(len(increases) and set(["price_group", "inicio", "fin_ciclo", "escalon", "activa_hoy"]) <= set(increases.columns)
          and (increases["activa_hoy"] == (pd.PeriodIndex(increases["fin_ciclo"], freq="M") >= current).astype(int)).all(),
          f"{len(increases)} price increases detected with the detector of step 3.1, and whether their cycle is still open")
    terms = tables["plazo_mes"]
    check(set(terms["plazo_anios"]) == {1, 2, 3} and np.allclose(terms.groupby("mes")["parte_usd"].sum(), 1.0),
          "the three terms, their shares adding up to 1 every month")
    trends = tables["tendencias"]
    check({"vence_usd", "tasa_unidades", "uplift", "adquisicion_unidades", "softcancel_primer_mes"} <= set(trends["kpi"])
          and trends["tendencia"].isin([RISING, "baja", STABLE, TOO_SHORT]).all(),
          f"{len(trends)} KPIs with their trend: {trends['tendencia'].value_counts().to_dict()}")
    check(os.path.exists(analysis["markdown"]) and len(analysis["charts"]) >= 8 and "VALORACIÓN" in console,
          f"the markdown and {len(analysis['charts'])} charts are written, the summary is on screen")


def test_the_stages() -> None:
    print("F · the stages")
    configuration = synthetic_with()
    results = {}
    console = console_of(lambda: results.update(run_stages(configuration, StagesToRun(data=True, analysis=True, forecast=False))))
    check("analysis" in results and "forecast" not in results and "dataset written" in console,
          "data + analysis: the dataset is written and described, no block runs")
    monthly = read_plain_table("e1_pipeline_mes", configuration)
    check(len(monthly) == len(results["analysis"]["tables"]["pipeline_mes"]) and os.path.exists(results["analysis"]["markdown"]),
          f"{configuration.table_prefix}e1_pipeline_mes is in SQL and ANALISIS_pipeline.md on disk")
    only_analysis = synthetic_with(sql_engine=configuration.sql_engine)
    again = {}
    console = console_of(lambda: again.update(run_stages(only_analysis, StagesToRun(data=False, analysis=True, forecast=False))))
    check("analysis" in again and "the SQL of the pipeline is not run again" in console,
          "analysis alone reads the dataset written and describes it")
    check(stages_of_the_command_line(["sin_analisis"]).analysis is False
          and stages_of_the_command_line(["escenario"]).analysis is False
          and stages_of_the_command_line(["solo_analisis"]) == StagesToRun(data=False, analysis=True, forecast=False, report=False)
          and stages_of_the_command_line([]).analysis is True,
          "the words of the command line: sin_analisis, escenario (no analysis), solo_analisis")


if __name__ == "__main__":
    test_the_pipeline_adds_up()
    test_the_trend()
    test_month_against_month()
    test_the_dated_states()
    test_the_like_real_extract()
    test_the_stages()
    finish()
