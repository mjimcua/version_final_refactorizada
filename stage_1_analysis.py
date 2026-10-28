"""
stage_1_analysis.py — STAGE 1 · THE ANALYSIS OF THE PIPELINE: what the raw material of the forecast looks like, before
any number of business is made with it (28-oct-2026, PLAN_etapas.md).

MISSION: describe the pipeline, past and future, so its trends and its evolution are seen before predicting: how much
money there is, whether it grows against the year before, its rhythm along the year (the seasonality of what falls
due), the share of 1, 2 and 3-year licences, the acquisition and its trend, whether the composition is changing, the
renewal rate and the uplift as they really were, the price increases that happened, the customer states and how early
the softcancels appear. Everything here is descriptive and comes from the pipeline alone: tables, numeric summaries
and charts of the evolution in time, and a simple regression line on what should be reasonably stable, to say
whether it is stable, rising or falling.

WHAT IS CLOSED, WHAT IS FUTURE, WHAT IS COMPLETE
  closed      a month before the current one: its pipeline fell due and its result (what renewed) is known
  future      the current month and the ones after it: their pipeline is known, their result is not
  complete    a future month whose 1-year licences have all been sold or renewed already (its origin month,
              12 months before, is closed): current + 11 at most. Later months still grow with every month that
              closes, so they are not compared with the year before.

THE SECTIONS (one table each, written as sff_e1_* and told in <output_folder>/analisis/ANALISIS_pipeline.md):
  e1_pipeline_mes            per month: units and USD due, renewed, rate, uplift, the same month a year before
  e1_pipeline_anio           per year: the money, the growth against the year before on comparable months
  e1_plazo_mes               per month and term: the share of 1, 2 and 3-year licences
  e1_tasa_mes_por            per closed month and dimension (total, region, term, origin): the real renewal rate
  e1_mes_contra_mes          the last closed month against the same month a year before (and the last 12 closed months
                             against the 12 before): where the differences are, by dimension, with the renewed USD
                             split into the effect of the pipeline, of the rate and of the uplift
  e1_uplift_mes              per closed month: the uplift (exact base), the isolated one, the groups in a price increase
  e1_subidas_precio          the price increases detected (the same detector as step 3.1), biggest first
  e1_adquisicion_mes         per month of sale and term: the acquisitions sold (units, USD they will fall due at)
  e1_composicion_anual       per year, dimension and value: the share of the USD due and its change
  e1_composicion_cambio      per year and dimension: how much the composition moved (Σ |Δ share| / 2)
  e1_estados_mes             per month and customer state: the share of the units due in it (final or seen so far)
  e1_estados_tempranos       per due month and dated state: the share already in the state in its first month(s)
  e1_estados_horizonte       per future month and dated state: what is visible today against the same horizon a year ago
  e1_retail_to_subscription  per closed month: the retail to subscription (the other universe)
  e1_transiciones_plazo      per year and origin term: to which term the renewals went
  e1_tendencias              one row per KPI: level, last 12 months against the 12 before, slope per year with its
                             significance (stable · rising · falling), seasonality (amplitude, high and low months)

THE INTERFACE:
  analysis = analyse_the_pipeline(raw, configuration)      the tables, the charts and the markdown
  analysis["tables"][name]   analysis["charts"]   analysis["markdown"]   analysis["figures"]

OVERLAPS, NOTED FOR THE REFACTORING (PLAN_etapas.md): chapter 1 of the report (the real data), 8.2 (the rate by
year), 8.5 (the composition), 8.9 (the increases detected), 8.10 (the term transitions) and the data profile of 8.6
describe the same raw from the core. They stay until H8; this stage is the one that describes the raw.
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import os
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from block_1_preparation import write_plain_table
from block_3_price import closed_view_of_fine_table
from config import (ACTIVE_FLAG_VALUES, CALENDAR_ROLE_COLUMN, Config, negative_states, parse_month, region_columns_of)
from graficos import (AQUA, BLUE, GRID, INK, INK_MUTED, INK_SECONDARY, NEUTRAL_FILL, ORANGE, VIOLET, money_label,
                      new_figure)
from graficos import save as save_png
from price_increases import increase_calendar, pending_steps, price_monitor
from term_transitions import term_years, transition_columns

# ─── named constants ─────────────────────────────────────────────────────────────
STAGE_1_LABEL = "E1"
STAGE_1_NAME = "ANALYSIS OF THE PIPELINE"
STAGE_1_PURPOSE = ("describe the pipeline, past and future, before predicting it: how much there is, whether it grows, its "
                   "rhythm along the year, the terms, the acquisition, the composition, the rate, the uplift and the price "
                   "increases, the customer states and the early softcancels; every KPI with its trend")
STAGE_1_ACTIONS = ["the rows of the pipeline: closed, future and complete months",
                   "the pipeline by month and by year, against the year before",
                   "the share of every term",
                   "the real renewal rate by month, total and by dimension",
                   "the last closed month against the same month a year before: where the differences are",
                   "the uplift and the price increases detected",
                   "the acquisition by month of sale",
                   "the composition of the pipeline by year and its change",
                   "the customer states: by month, in the first months, and at the same horizon a year ago",
                   "the retail to subscription and the term transitions",
                   "the trend of every KPI (regression line and seasonality)",
                   "write the tables (sff_e1_*), draw the charts and tell it (ANALISIS_pipeline.md)"]
STAGE_1_OUTPUT = "sff_e1_* · <output_folder>/analisis/ANALISIS_pipeline.md and its charts"
ANALYSIS_FOLDER = "analisis"
MARKDOWN_NAME = "ANALISIS_pipeline.md"
MONTHS_PER_YEAR = 12
PERCENTAGE_POINTS = 100.0
CLOSED, FUTURE = "cerrado", "futuro"
ACQUISITION, RETENTION = "adquisicion", "retencion"
TOTAL = "total"
OTHERS = "otros"
MONTH_NAMES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
YEAR_COLOURS = ["#c9c7bf", "#a9a69c", "#7f7c72", BLUE, ORANGE, VIOLET]      # older years in greys, the last ones in colour
RISING, FALLING, STABLE, TOO_SHORT = "sube", "baja", "estable", "pocos_meses"
NEGLIGIBLE = 1e-9                   # a slope or a month effect below this share of the values is rounding, not a pattern

# the tables of the stage (table_prefix + …)
TABLE_PIPELINE_BY_MONTH = "e1_pipeline_mes"
TABLE_PIPELINE_BY_YEAR = "e1_pipeline_anio"
TABLE_TERM_BY_MONTH = "e1_plazo_mes"
TABLE_RATE_BY_MONTH = "e1_tasa_mes_por"
TABLE_MONTH_AGAINST_MONTH = "e1_mes_contra_mes"
TABLE_UPLIFT_BY_MONTH = "e1_uplift_mes"
TABLE_PRICE_INCREASES = "e1_subidas_precio"
TABLE_ACQUISITION_BY_MONTH = "e1_adquisicion_mes"
TABLE_COMPOSITION_BY_YEAR = "e1_composicion_anual"
TABLE_COMPOSITION_CHANGE = "e1_composicion_cambio"
TABLE_STATES_BY_MONTH = "e1_estados_mes"
TABLE_EARLY_STATES = "e1_estados_tempranos"
TABLE_STATES_AT_HORIZON = "e1_estados_horizonte"
TABLE_RETAIL_TO_SUBSCRIPTION = "e1_retail_to_subscription"
TABLE_TERM_TRANSITIONS = "e1_transiciones_plazo"
TABLE_TRENDS = "e1_tendencias"

# the derived columns of the rows of the pipeline (an underscore: never written)
MONTH, YEAR, MONTH_OF_YEAR = "_mes", "_anio", "_mes_del_anio"
IS_CLOSED, IS_COMPLETE, TERM_YEARS, IS_ACQUISITION, ORIGIN = "_cerrado", "_completa", "_plazo_anios", "_adquisicion", "_origen"


# ═══════════════════════════════════════════════════════════════════════════════════
# THE ROWS OF THE PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════════

def pipeline_rows_of(raw: pd.DataFrame, configuration: Config) -> tuple:
    """The rows of the renewal universe and the ones of the time series universe (retail to subscription), with
    the month as a Period, every measure as a number (a null is 0), the year, the calendar month, whether the month
    is closed and whether its pipeline is complete, the years of the term, and whether the row is an acquisition.
    Only the columns this stage reads are kept."""
    current = configuration.calendar_boundaries()["current"]
    period_column = configuration.period_col
    months_by_value = {value: parse_month(value) for value in raw[period_column].dropna().unique()}
    months = pd.PeriodIndex(raw[period_column].map(months_by_value), freq="M")

    measures = [configuration.pipeline_units_col, configuration.pipeline_usd_col, configuration.renewed_units_col,
                configuration.renewed_usd_col]
    optional_measures = [configuration.renewed_pipeline_usd_col, configuration.isolated_renewed_units_col,
                         configuration.isolated_renewed_usd_col, configuration.isolated_renewed_pipeline_usd_col]
    maturation_columns = [f"{state}_month_{k}" for state in configuration.maturation_dims
                          for k in range(configuration.maturation_months + 1)]
    transition_measures = [column for _, _, units_column, usd_column in transition_columns(configuration)
                           for column in (units_column, usd_column)]
    dimensions = (list(configuration.business_mandatory_dims) + list(configuration.structural_timevarying_dims)
                  + region_columns_of(configuration) + list(configuration.price_group_dims)
                  + [configuration.term_column, configuration.acquisition_column, configuration.flag_time_series_col])
    for measure in configuration.closed_month_measures:
        optional_measures.append(measure.raw_column)
    kept = []
    for column in measures + optional_measures + maturation_columns + transition_measures + dimensions:
        if column and column in raw.columns and column not in kept:
            kept.append(column)
    rows = raw[kept].copy()
    numeric = [column for column in measures + optional_measures + maturation_columns + transition_measures
               if column in rows.columns]
    for column in numeric:
        rows[column] = pd.to_numeric(rows[column], errors="coerce").fillna(0.0).astype(float)
    rows[period_column] = months                 # the month as a Period, under its own name (the price monitor reads it there)
    rows[MONTH] = months
    rows[YEAR] = months.year
    rows[MONTH_OF_YEAR] = months.month
    rows[IS_CLOSED] = months < current
    rows[IS_COMPLETE] = months < current + MONTHS_PER_YEAR
    rows[CALENDAR_ROLE_COLUMN] = configuration.role_of_months(months)
    if configuration.term_column and configuration.term_column in rows.columns:
        rows[TERM_YEARS] = term_years(rows[configuration.term_column]).fillna(1).astype(int)
    else:
        rows[TERM_YEARS] = 1
    if configuration.acquisition_column and configuration.acquisition_column in rows.columns:
        values = rows[configuration.acquisition_column]
        rows[IS_ACQUISITION] = values.isin(configuration.acquisition_values) | values.astype(str).isin(
            [str(value) for value in configuration.acquisition_values])
    else:
        rows[IS_ACQUISITION] = False
    rows[ORIGIN] = np.where(rows[IS_ACQUISITION], ACQUISITION, RETENTION)

    flag_column = configuration.flag_time_series_col
    is_time_series = rows[flag_column].isin(ACTIVE_FLAG_VALUES) if flag_column in rows.columns else pd.Series(False, index=rows.index)
    return rows[~is_time_series].copy(), rows[is_time_series].copy()


def month_text(months) -> pd.Series:
    return pd.Series([str(month) for month in months], index=getattr(months, "index", None))


def full_month_range(months) -> pd.PeriodIndex:
    return pd.period_range(min(months), max(months), freq="M")


def a_year_before(series: pd.Series) -> pd.Series:
    """The value of the same month a year before (the series indexed by Period, every month present)."""
    shifted = series.copy()
    shifted.index = shifted.index + MONTHS_PER_YEAR
    return shifted.reindex(series.index)


def change_against(now: pd.Series, before: pd.Series) -> pd.Series:
    """now / before − 1, NaN when there is nothing before."""
    return now / before.where(before > 0) - 1.0


def rate_band(renewed: pd.Series, due: pd.Series, z: float) -> tuple:
    """The rate and its binomial band (z √(p (1 − p) / n))."""
    rate = renewed / due.where(due > 0)
    error = z * np.sqrt(rate * (1 - rate) / due.where(due > 0))
    return rate, rate - error, rate + error


# ═══════════════════════════════════════════════════════════════════════════════════
# THE TREND OF A MONTHLY SERIES: a regression line and the month effect
# ═══════════════════════════════════════════════════════════════════════════════════

def trend_of(monthly: pd.Series, configuration: Config, in_points: bool = False) -> dict:
    """The simple description of a monthly series (indexed by Period; NaN months are left out): its level, the mean
    of the last 12 months against the 12 before, the regression line on time (slope per year, in points when the
    series is a share, and relative to the mean otherwise) with its p-value, the verdict (rising, falling or stable),
    and the month effect on the detrended series (an F test over the calendar months; amplitude, high and low
    months) when there are enough months to see every season twice."""
    series = monthly.dropna().astype(float)
    series = series[np.isfinite(series)]
    result = {"meses": int(len(series)), "primer_mes": str(series.index.min()) if len(series) else "",
              "ultimo_mes": str(series.index.max()) if len(series) else "",
              "media": float(series.mean()) if len(series) else np.nan,
              "media_ultimos_12": np.nan, "media_12_anteriores": np.nan, "variacion_12m": np.nan,
              "pendiente_anual": np.nan, "pendiente_relativa_anual": np.nan, "p_valor_tendencia": np.nan,
              "tendencia": TOO_SHORT, "estacional": 0, "p_valor_mes": np.nan, "amplitud_estacional": np.nan,
              "meses_alto": "", "meses_bajo": "", "_fitted": pd.Series(dtype=float), "_month_effects": pd.Series(dtype=float)}
    if len(series) >= 2 * MONTHS_PER_YEAR:
        last, before = series.iloc[-MONTHS_PER_YEAR:], series.iloc[-2 * MONTHS_PER_YEAR:-MONTHS_PER_YEAR]
        result["media_ultimos_12"], result["media_12_anteriores"] = float(last.mean()), float(before.mean())
        result["variacion_12m"] = (float(last.mean() - before.mean()) if in_points
                                   else float(last.mean() / before.mean() - 1.0) if before.mean() > 0 else np.nan)
    elif len(series) >= MONTHS_PER_YEAR:
        result["media_ultimos_12"] = float(series.iloc[-MONTHS_PER_YEAR:].mean())
    if len(series) < configuration.analysis_trend_min_months:
        return result

    # the regression line: the value on the time in years since the first month
    first_ordinal = series.index.min().ordinal
    time_in_years = np.array([(month.ordinal - first_ordinal) / MONTHS_PER_YEAR for month in series.index])
    values = series.to_numpy()
    design = np.column_stack([np.ones_like(time_in_years), time_in_years])
    coefficients, _, _, _ = np.linalg.lstsq(design, values, rcond=None)
    fitted = design @ coefficients
    residuals = values - fitted
    degrees_of_freedom = max(len(values) - 2, 1)
    residual_variance = float(np.sum(residuals ** 2) / degrees_of_freedom)
    slope_se = float(np.sqrt(residual_variance * np.linalg.inv(design.T @ design)[1, 1])) if residual_variance > 0 else 0.0
    slope = float(coefficients[1])
    mean = float(values.mean())
    scale_of_values = max(abs(mean), float(np.abs(values).max()), 1e-12)
    if abs(slope) < NEGLIGIBLE * scale_of_values:
        p_value = 1.0          # a flat series (a constant, or one that moves by rounding alone) has no trend
    elif slope_se > 0:
        p_value = float(2 * stats.t.sf(abs(slope / slope_se), degrees_of_freedom))
    else:
        p_value = 0.0          # an exact line: no residual at all
    result["pendiente_anual"] = slope * (PERCENTAGE_POINTS if in_points else 1.0)
    result["pendiente_relativa_anual"] = slope / mean if (not in_points and mean != 0) else np.nan
    result["p_valor_tendencia"] = p_value
    result["tendencia"] = (RISING if slope > 0 else FALLING) if p_value < configuration.dynamics_significance else STABLE
    result["_fitted"] = pd.Series(fitted, index=series.index)

    # the month effect, on the detrended series: the twelve calendar months against each other (F test)
    if len(series) < configuration.analysis_season_min_months:
        return result
    detrended = pd.DataFrame({"mes": [month.month for month in series.index], "residuo": residuals})
    by_month = detrended.groupby("mes")["residuo"]
    month_effect, month_count = by_month.mean(), by_month.size()
    between = float(np.sum(month_count * month_effect ** 2))
    within = float(np.sum((detrended["residuo"] - detrended["mes"].map(month_effect)) ** 2))
    months_present = len(month_effect)
    between_df, within_df = max(months_present - 1, 1), max(len(values) - months_present - 1, 1)
    f_statistic = (between / between_df) / (within / within_df) if within > 0 else 0.0
    month_p_value = float(stats.f.sf(f_statistic, between_df, within_df)) if within > 0 else 0.0
    month_error = np.sqrt(within / within_df / month_count)
    scale = PERCENTAGE_POINTS if in_points else (1.0 / mean if mean != 0 else np.nan)
    amplitude = float(month_effect.max() - month_effect.min())
    if amplitude < NEGLIGIBLE * scale_of_values:          # the months differ by rounding alone: no season
        month_p_value = 1.0
    result["estacional"] = int(month_p_value < configuration.dynamics_significance)
    result["p_valor_mes"] = month_p_value
    result["amplitud_estacional"] = float((month_effect.max() - month_effect.min()) * scale)
    result["meses_alto"] = ",".join(str(int(month)) for month in month_effect.index if month_effect[month] > 2 * month_error[month])
    result["meses_bajo"] = ",".join(str(int(month)) for month in month_effect.index if -month_effect[month] > 2 * month_error[month])
    result["_month_effects"] = month_effect * scale
    return result


# ═══════════════════════════════════════════════════════════════════════════════════
# THE PIPELINE BY MONTH AND BY YEAR
# ═══════════════════════════════════════════════════════════════════════════════════

def pipeline_by_month(rows: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """One row per month of the extract: rows, units and USD due, renewed (closed months), the rate in units and in
    USD, the uplift on its exact base (when the extract carries it), and the same month a year before."""
    due_units, due_usd = configuration.pipeline_units_col, configuration.pipeline_usd_col
    renewed_units, renewed_usd = configuration.renewed_units_col, configuration.renewed_usd_col
    exact_base = configuration.renewed_pipeline_usd_col if configuration.renewed_pipeline_usd_col in rows.columns else None
    summed = rows.groupby(MONTH).agg(filas=(due_units, "size"), vencen_unidades=(due_units, "sum"), vence_usd=(due_usd, "sum"),
                                     renovadas_unidades=(renewed_units, "sum"), renovado_usd=(renewed_usd, "sum"),
                                     **({"base_uplift_usd": (exact_base, "sum")} if exact_base else {}))
    summed = summed.reindex(full_month_range(summed.index), fill_value=0.0)
    summed["filas"] = summed["filas"].astype(int)
    current = configuration.calendar_boundaries()["current"]
    closed = summed.index < current
    monthly = pd.DataFrame(index=summed.index)
    monthly["mes"] = month_text(summed.index).to_numpy()
    monthly["anio"] = summed.index.year
    monthly["mes_del_anio"] = summed.index.month
    monthly["estado"] = np.where(closed, CLOSED, FUTURE)
    monthly["completa"] = (summed.index < current + MONTHS_PER_YEAR).astype(int)
    monthly["filas"] = summed["filas"]
    monthly["vencen_unidades"] = summed["vencen_unidades"]
    monthly["vence_usd"] = summed["vence_usd"]
    monthly["renovadas_unidades"] = summed["renovadas_unidades"].where(closed)
    monthly["renovado_usd"] = summed["renovado_usd"].where(closed)
    monthly["tasa_unidades"] = (monthly["renovadas_unidades"] / monthly["vencen_unidades"].where(monthly["vencen_unidades"] > 0)).where(closed)
    monthly["tasa_usd"] = (monthly["renovado_usd"] / monthly["vence_usd"].where(monthly["vence_usd"] > 0)).where(closed)
    if exact_base:
        monthly["uplift"] = (summed["renovado_usd"] / summed["base_uplift_usd"].where(summed["base_uplift_usd"] > 0)).where(closed)
    else:
        monthly["uplift"] = np.nan
    monthly["vence_usd_ano_anterior"] = a_year_before(monthly["vence_usd"])
    monthly["vencen_unidades_ano_anterior"] = a_year_before(monthly["vencen_unidades"])
    monthly["variacion_usd_vs_ano_anterior"] = change_against(monthly["vence_usd"], monthly["vence_usd_ano_anterior"])
    monthly["variacion_unidades_vs_ano_anterior"] = change_against(monthly["vencen_unidades"], monthly["vencen_unidades_ano_anterior"])
    monthly["renovado_usd_ano_anterior"] = a_year_before(monthly["renovado_usd"])
    monthly["tasa_unidades_ano_anterior"] = a_year_before(monthly["tasa_unidades"])
    return monthly.reset_index(drop=True)


def pipeline_by_year(monthly: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """One row per year: its closed and future months, the money due and renewed, the rate and the uplift of its
    closed months, and the growth against the year before measured on COMPARABLE months: the months of the year
    that are closed or complete, against the same months of the year before."""
    current = configuration.calendar_boundaries()["current"]
    rows = []
    for year, of_year in monthly.groupby("anio"):
        # comparable: a complete month (closed or future) whose same month a year before is in the extract
        comparable = of_year[(of_year["completa"] == 1) & of_year["vence_usd_ano_anterior"].notna()]
        closed = of_year[of_year["estado"] == CLOSED]
        same_months_before = comparable["vence_usd_ano_anterior"].sum()
        same_units_before = comparable["vencen_unidades_ano_anterior"].sum()
        row = {"anio": int(year),
               "estado": CLOSED if len(closed) == len(of_year) else (FUTURE if closed.empty else "en_curso"),
               "meses": int(len(of_year)), "meses_cerrados": int(len(closed)),
               "meses_comparables": int(len(comparable)),
               "vence_usd": float(of_year["vence_usd"].sum()), "vencen_unidades": float(of_year["vencen_unidades"].sum()),
               "vence_usd_cerrado": float(closed["vence_usd"].sum()),
               "vence_usd_futuro": float(of_year.loc[of_year["estado"] == FUTURE, "vence_usd"].sum()),
               "renovado_usd": float(closed["renovado_usd"].sum()) if len(closed) else np.nan,
               "renovadas_unidades": float(closed["renovadas_unidades"].sum()) if len(closed) else np.nan,
               "tasa_unidades": (float(closed["renovadas_unidades"].sum() / closed["vencen_unidades"].sum())
                                 if len(closed) and closed["vencen_unidades"].sum() > 0 else np.nan),
               "tasa_usd": (float(closed["renovado_usd"].sum() / closed["vence_usd"].sum())
                            if len(closed) and closed["vence_usd"].sum() > 0 else np.nan),
               "vence_usd_comparable": float(comparable["vence_usd"].sum()),
               "vence_usd_mismos_meses_ano_anterior": float(same_months_before),
               "vencen_unidades_comparable": float(comparable["vencen_unidades"].sum()),
               "vencen_unidades_mismos_meses_ano_anterior": float(same_units_before)}
        row["crecimiento_usd_vs_ano_anterior"] = (row["vence_usd_comparable"] / same_months_before - 1.0
                                                 if same_months_before > 0 and len(comparable) else np.nan)
        row["crecimiento_unidades_vs_ano_anterior"] = (row["vencen_unidades_comparable"] / same_units_before - 1.0
                                                      if same_units_before > 0 and len(comparable) else np.nan)
        uplift_months = closed["uplift"].dropna()
        row["uplift"] = (float((closed["renovado_usd"]).sum() / (closed["renovado_usd"] / closed["uplift"]).sum())
                         if len(uplift_months) and (closed["renovado_usd"] / closed["uplift"]).sum() > 0 else np.nan)
        rows.append(row)
    yearly = pd.DataFrame(rows)
    yearly.attrs["current_year"] = current.year
    return yearly


# ═══════════════════════════════════════════════════════════════════════════════════
# THE TERMS, THE RATE, THE UPLIFT AND THE PRICE INCREASES
# ═══════════════════════════════════════════════════════════════════════════════════

def term_by_month(rows: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """One row per month and term (years of the licence): units and USD due and their share of the month."""
    if not configuration.term_column:
        return pd.DataFrame()
    due_units, due_usd = configuration.pipeline_units_col, configuration.pipeline_usd_col
    summed = rows.groupby([MONTH, TERM_YEARS]).agg(vencen_unidades=(due_units, "sum"), vence_usd=(due_usd, "sum")).reset_index()
    totals = summed.groupby(MONTH)[["vencen_unidades", "vence_usd"]].transform("sum")
    summed["parte_unidades"] = summed["vencen_unidades"] / totals["vencen_unidades"].where(totals["vencen_unidades"] > 0)
    summed["parte_usd"] = summed["vence_usd"] / totals["vence_usd"].where(totals["vence_usd"] > 0)
    current = configuration.calendar_boundaries()["current"]
    table = pd.DataFrame({"mes": month_text(summed[MONTH]).to_numpy(), "anio": [month.year for month in summed[MONTH]],
                          "estado": np.where(summed[MONTH] < current, CLOSED, FUTURE),
                          "completa": (summed[MONTH] < current + MONTHS_PER_YEAR).astype(int),
                          "plazo_anios": summed[TERM_YEARS].astype(int), "vencen_unidades": summed["vencen_unidades"],
                          "vence_usd": summed["vence_usd"], "parte_unidades": summed["parte_unidades"],
                          "parte_usd": summed["parte_usd"]})
    return table.sort_values(["mes", "plazo_anios"]).reset_index(drop=True)


def term_dimension(configuration: Config) -> list:
    """The term as a dimension: the years of the licence (plazo_anios), unless the term column is already a mandatory
    dim of the business (then it is read under its own name, and not twice). Empty without a term column."""
    if not configuration.term_column:
        return []
    if configuration.term_column in configuration.business_mandatory_dims:
        return [(configuration.term_column, configuration.term_column)]
    return [("plazo_anios", TERM_YEARS)]


def rate_dimensions(rows: pd.DataFrame, configuration: Config) -> list:
    """The dimensions the rate is broken by: the total, the coarsest region level, the term and the origin."""
    dimensions = [(TOTAL, None)]
    region = region_columns_of(configuration)[0]
    if region in rows.columns:
        dimensions.append((region, region))
    dimensions += [(name, column) for name, column in term_dimension(configuration) if name not in dict(dimensions)]
    if configuration.acquisition_column and configuration.acquisition_column in rows.columns:
        dimensions.append(("origen", ORIGIN))
    return dimensions


def rate_by_month(rows: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """One row per closed month, dimension and value: units due, renewed, the rate with its binomial band, the USD rate."""
    due_units, due_usd = configuration.pipeline_units_col, configuration.pipeline_usd_col
    renewed_units, renewed_usd = configuration.renewed_units_col, configuration.renewed_usd_col
    closed = rows[rows[IS_CLOSED]]
    parts = []
    for name, column in rate_dimensions(rows, configuration):
        keys = [MONTH] + ([column] if column else [])
        summed = closed.groupby(keys).agg(vencen_unidades=(due_units, "sum"), renovadas_unidades=(renewed_units, "sum"),
                                          vence_usd=(due_usd, "sum"), renovado_usd=(renewed_usd, "sum")).reset_index()
        summed["dimension"] = name
        summed["valor"] = summed[column].astype(str) if column else TOTAL
        parts.append(summed[[MONTH, "dimension", "valor", "vencen_unidades", "renovadas_unidades", "vence_usd", "renovado_usd"]])
    table = pd.concat(parts, ignore_index=True)
    rate, low, high = rate_band(table["renovadas_unidades"], table["vencen_unidades"], configuration.z)
    table["tasa_unidades"], table["tasa_binomial_baja"], table["tasa_binomial_alta"] = rate, low, high
    table["tasa_usd"] = table["renovado_usd"] / table["vence_usd"].where(table["vence_usd"] > 0)
    table.insert(0, "mes", month_text(table[MONTH]).to_numpy())
    table.insert(1, "anio", [month.year for month in table[MONTH]])
    return table.drop(columns=[MONTH]).sort_values(["dimension", "valor", "mes"]).reset_index(drop=True)


LAST_MONTH, LAST_12_MONTHS = "ultimo_mes", "ultimos_12_meses"


def comparison_dimensions(rows: pd.DataFrame, configuration: Config) -> list:
    """The dimensions the month-against-month comparison is broken by: the total, every mandatory dim of the business,
    the term, the origin and every customer state (in the state or not)."""
    dimensions = [(TOTAL, None)] + [(column, column) for column in configuration.business_mandatory_dims if column in rows.columns]
    dimensions += [(name, column) for name, column in term_dimension(configuration) if name not in dict(dimensions)]
    if configuration.acquisition_column and configuration.acquisition_column in rows.columns:
        dimensions.append(("origen", ORIGIN))
    dimensions += [(state, state) for state in configuration.structural_timevarying_dims if state in rows.columns]
    return dimensions


def month_against_month(rows: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """Where the differences are: the last closed month against the same month a year before, and the last 12 closed
    months against the 12 before, by dimension and value. Every row carries what fell due and what renewed in both,
    the rate (units), the uplift, and the renewed USD split into three effects that add up to its change:
        renewed = due USD × base rate × uplift     (base rate: the share of the USD due that renewed, at due price)
        pipeline effect   = Δ due USD × base rate before × uplift before      (more or less fell due)
        rate effect       = due USD now × Δ base rate × uplift before         (it renewed more or less)
        uplift effect     = due USD now × base rate now × Δ uplift            (it renewed at another price)
    Without the exact base of the uplift in the extract, the rate and the uplift effects are one: the yield effect."""
    due_units, due_usd = configuration.pipeline_units_col, configuration.pipeline_usd_col
    renewed_units, renewed_usd = configuration.renewed_units_col, configuration.renewed_usd_col
    exact_base = configuration.renewed_pipeline_usd_col if configuration.renewed_pipeline_usd_col in rows.columns else None
    closed = rows[rows[IS_CLOSED]]
    if closed.empty:
        return pd.DataFrame()
    last_closed = closed[MONTH].max()
    windows = [(LAST_MONTH, [last_closed], [last_closed - MONTHS_PER_YEAR])]
    if last_closed.ordinal - closed[MONTH].min().ordinal >= 2 * MONTHS_PER_YEAR - 1:
        now_months = [last_closed - offset for offset in range(MONTHS_PER_YEAR)]
        windows.append((LAST_12_MONTHS, now_months, [month - MONTHS_PER_YEAR for month in now_months]))
    measures = {"vencen_unidades": (due_units, "sum"), "vence_usd": (due_usd, "sum"), "renovadas_unidades": (renewed_units, "sum"),
                "renovado_usd": (renewed_usd, "sum"), **({"base_uplift_usd": (exact_base, "sum")} if exact_base else {})}
    parts = []
    for comparison, now_months, before_months in windows:
        now_rows, before_rows = closed[closed[MONTH].isin(now_months)], closed[closed[MONTH].isin(before_months)]
        for name, column in comparison_dimensions(rows, configuration):
            keys = [column] if column else []
            if keys:
                now = now_rows.groupby(keys).agg(**measures)
                before = before_rows.groupby(keys).agg(**measures)
                now.index, before.index = now.index.astype(str), before.index.astype(str)
            else:
                now = pd.DataFrame([now_rows.agg({source: how for _, (source, how) in measures.items()}).rename(
                    {source: measure for measure, (source, _) in measures.items()})], index=[TOTAL])
                before = pd.DataFrame([before_rows.agg({source: how for _, (source, how) in measures.items()}).rename(
                    {source: measure for measure, (source, _) in measures.items()})], index=[TOTAL])
            values = now.index.union(before.index)
            now, before = now.reindex(values, fill_value=0.0), before.reindex(values, fill_value=0.0)
            part = pd.DataFrame({"comparacion": comparison, "mes_hoy": f"{min(now_months)}..{max(now_months)}" if len(now_months) > 1 else str(now_months[0]),
                                 "mes_antes": f"{min(before_months)}..{max(before_months)}" if len(before_months) > 1 else str(before_months[0]),
                                 "dimension": name, "valor": values}, index=values)
            for measure in ("vencen_unidades", "vence_usd", "renovadas_unidades", "renovado_usd"):
                part[f"{measure}_hoy"], part[f"{measure}_antes"] = now[measure], before[measure]
                part[f"{measure}_diferencia"] = now[measure] - before[measure]
            part["tasa_unidades_hoy"] = now["renovadas_unidades"] / now["vencen_unidades"].where(now["vencen_unidades"] > 0)
            part["tasa_unidades_antes"] = before["renovadas_unidades"] / before["vencen_unidades"].where(before["vencen_unidades"] > 0)
            part["tasa_unidades_diferencia_pp"] = (part["tasa_unidades_hoy"] - part["tasa_unidades_antes"]) * PERCENTAGE_POINTS
            if exact_base:
                base_rate_now = now["base_uplift_usd"] / now["vence_usd"].where(now["vence_usd"] > 0)
                base_rate_before = before["base_uplift_usd"] / before["vence_usd"].where(before["vence_usd"] > 0)
                uplift_now = now["renovado_usd"] / now["base_uplift_usd"].where(now["base_uplift_usd"] > 0)
                uplift_before = before["renovado_usd"] / before["base_uplift_usd"].where(before["base_uplift_usd"] > 0)
            else:
                base_rate_now = now["renovado_usd"] / now["vence_usd"].where(now["vence_usd"] > 0)
                base_rate_before = before["renovado_usd"] / before["vence_usd"].where(before["vence_usd"] > 0)
                uplift_now = pd.Series(1.0, index=values)
                uplift_before = pd.Series(1.0, index=values)
            part["uplift_hoy"], part["uplift_antes"] = (uplift_now, uplift_before) if exact_base else (np.nan, np.nan)
            # a value with nothing before (or nothing now) has no rate to compare: its whole change is pipeline
            rate_before = base_rate_before.fillna(base_rate_now).fillna(0.0)
            rate_now = base_rate_now.fillna(rate_before)
            lift_before = uplift_before.fillna(uplift_now).fillna(1.0)
            lift_now = uplift_now.fillna(lift_before)
            part["efecto_pipeline_usd"] = (now["vence_usd"] - before["vence_usd"]) * rate_before * lift_before
            part["efecto_tasa_usd"] = now["vence_usd"] * (rate_now - rate_before) * lift_before
            part["efecto_uplift_usd"] = now["vence_usd"] * rate_now * (lift_now - lift_before)
            # the three effects add up to the change of the renewed USD; what rounding leaves goes to the rate effect
            part["efecto_tasa_usd"] += part["renovado_usd_diferencia"] - (part["efecto_pipeline_usd"] + part["efecto_tasa_usd"] + part["efecto_uplift_usd"])
            parts.append(part)
    table = pd.concat(parts, ignore_index=True)
    table["_peso"] = table["renovado_usd_diferencia"].abs()
    table["_orden"] = table["dimension"].map({name: position for position, (name, _) in enumerate(comparison_dimensions(rows, configuration))})
    table = table.sort_values(["comparacion", "_orden", "_peso"], ascending=[True, True, False])
    return table.drop(columns=["_peso", "_orden"]).reset_index(drop=True)


def uplift_and_increases(rows: pd.DataFrame, configuration: Config) -> dict:
    """The uplift of every closed month (renewed USD / what the renewers were worth: the exact base when the extract
    carries it, renewed units × the price of the row otherwise), the uplift of the ISOLATED renewals (no retention
    discounts), and the price increases detected with the same detector as step 3.1 (price_increases.py): the
    monthly table, the calendar of increases and the steps not confirmed yet."""
    due_units = configuration.pipeline_units_col
    view = closed_view_of_fine_table(rows, configuration)
    if view.empty:
        return {"monthly": pd.DataFrame(), "increases": pd.DataFrame(), "pending": pd.DataFrame(), "detector": ""}
    monitor = price_monitor(view, configuration)
    increases = increase_calendar(monitor, configuration)
    pending = pending_steps(monitor, configuration)
    monitor["period"] = pd.PeriodIndex(monitor["period"], freq="M")
    by_month = monitor.groupby("period").agg(renovado_usd=("renewed_USD", "sum"), base_uplift_usd=("uplift_base_USD", "sum"),
                                              grupos=("price_group", "nunique"),
                                              grupos_en_subida=("in_increase_cycle", lambda flags: int((flags == 1).sum())),
                                              subidas_que_empiezan=("price_increase_flag", lambda flags: int((flags == 1).sum())))
    in_cycle = monitor[monitor["in_increase_cycle"] == 1].groupby("period")["renewed_USD"].sum()
    by_month["usd_renovado_en_subida"] = in_cycle.reindex(by_month.index).fillna(0.0)
    by_month["parte_usd_en_subida"] = by_month["usd_renovado_en_subida"] / by_month["renovado_usd"].where(by_month["renovado_usd"] > 0)
    by_month["uplift"] = by_month["renovado_usd"] / by_month["base_uplift_usd"].where(by_month["base_uplift_usd"] > 0)
    # the isolated uplift of the month: its two sums, when the extract carries them
    isolated_usd, isolated_base = configuration.isolated_renewed_usd_col, configuration.isolated_renewed_pipeline_usd_col
    if isolated_usd in rows.columns and isolated_base in rows.columns:
        closed = rows[rows[IS_CLOSED]].groupby(MONTH)[[isolated_usd, isolated_base]].sum()
        closed = closed.reindex(by_month.index)
        by_month["uplift_aislado"] = closed[isolated_usd] / closed[isolated_base].where(closed[isolated_base] > 0)
    else:
        by_month["uplift_aislado"] = np.nan
    monthly = by_month.reset_index()
    monthly.insert(0, "mes", month_text(monthly["period"]).to_numpy())
    monthly.insert(1, "anio", [month.year for month in monthly["period"]])
    monthly = monthly.drop(columns=["period"])
    monthly["uplift_ano_anterior"] = a_year_before(pd.Series(monthly["uplift"].to_numpy(), index=by_month.index)).to_numpy()
    if len(increases):
        increases = increases.copy()
        increases["inicio"] = increases["inicio"].astype(str)
        increases["fin_ciclo"] = [str(pd.Period(start, freq="M") + configuration.price_cycle_months - 1) for start in increases["inicio"]]
        increases["activa_hoy"] = (pd.PeriodIndex(increases["fin_ciclo"], freq="M") >= configuration.calendar_boundaries()["current"]).astype(int)
    if len(pending):
        pending = pending.copy()
        for column in pending.columns:
            if pending[column].dtype == object or str(pending[column].dtype).startswith("period"):
                pending[column] = pending[column].astype(str)
    return {"monthly": monthly, "increases": increases, "pending": pending,
            "detector": monitor.attrs.get("detector_series", ""), "renewed_units_column": due_units}


# ═══════════════════════════════════════════════════════════════════════════════════
# THE ACQUISITION, BY MONTH OF SALE
# ═══════════════════════════════════════════════════════════════════════════════════

def acquisition_by_month(rows: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """One row per month of sale and term: the acquisitions sold that month (units and the USD they will fall due at).
    The month of sale of an acquisition is its due month minus the months of its term (12, 24 or 36). A sale month is
    OBSERVABLE for a term when its licences of that term fall due inside the extract (between its first and its last
    month) and the month of sale is closed; only observable months are compared and trended, and the 1-year
    acquisitions (the ones the forecast simulates, and most of them) are the headline series."""
    if not configuration.acquisition_column or not rows[IS_ACQUISITION].any():
        return pd.DataFrame()
    due_units, due_usd = configuration.pipeline_units_col, configuration.pipeline_usd_col
    current = configuration.calendar_boundaries()["current"]
    first_month, last_month = rows[MONTH].min(), rows[MONTH].max()
    acquired = rows[rows[IS_ACQUISITION]].copy()
    acquired["_mes_venta"] = acquired[MONTH] - (acquired[TERM_YEARS] * MONTHS_PER_YEAR).to_numpy()
    acquired = acquired[acquired["_mes_venta"] < current]
    if acquired.empty:
        return pd.DataFrame()
    by_term = acquired.groupby(["_mes_venta", TERM_YEARS]).agg(vendidas_unidades=(due_units, "sum"), vendido_usd=(due_usd, "sum")).reset_index()
    months = full_month_range(by_term["_mes_venta"])
    parts = []
    for term, of_term in by_term.groupby(TERM_YEARS):
        of_term = of_term.drop(columns=[TERM_YEARS]).set_index("_mes_venta").reindex(months).fillna(0.0)
        term_months = int(term) * MONTHS_PER_YEAR
        observable = (months + term_months >= first_month) & (months + term_months <= last_month) & (months < current)
        of_term["plazo_anios"] = int(term)
        of_term["observable"] = observable.astype(int)
        for measure in ("vendidas_unidades", "vendido_usd"):
            of_term[measure] = of_term[measure].where(observable)
            of_term[f"{measure}_ano_anterior"] = a_year_before(of_term[measure])
            of_term[f"variacion_{measure.split('_')[1] if measure.endswith('usd') else 'unidades'}_vs_ano_anterior"] = change_against(
                of_term[measure], of_term[f"{measure}_ano_anterior"])
        of_term.insert(0, "mes_venta", month_text(of_term.index).to_numpy())
        of_term.insert(1, "anio_venta", of_term.index.year)
        of_term.insert(2, "mes_del_anio", of_term.index.month)
        parts.append(of_term.reset_index(drop=True))
    result = pd.concat(parts, ignore_index=True)
    return result[["mes_venta", "anio_venta", "mes_del_anio", "plazo_anios", "observable", "vendidas_unidades", "vendido_usd",
                   "vendidas_unidades_ano_anterior", "vendido_usd_ano_anterior", "variacion_unidades_vs_ano_anterior",
                   "variacion_usd_vs_ano_anterior"]].sort_values(["plazo_anios", "mes_venta"]).reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════════
# THE COMPOSITION OF THE PIPELINE, BY YEAR
# ═══════════════════════════════════════════════════════════════════════════════════

def composition_dimensions(rows: pd.DataFrame, configuration: Config) -> list:
    """(name, column) of every dimension the composition is read by: the mandatory dims of the business, the term
    in years and the origin (acquisition or retention)."""
    dimensions = [(column, column) for column in configuration.business_mandatory_dims if column in rows.columns]
    dimensions += [(name, column) for name, column in term_dimension(configuration) if name not in dict(dimensions)]
    if configuration.acquisition_column and configuration.acquisition_column in rows.columns:
        dimensions.append(("origen", ORIGIN))
    return dimensions


def composition_by_year(rows: pd.DataFrame, configuration: Config) -> tuple:
    """Per year, dimension and value: the USD and units due, the share of the USD of the year, the share the year before
    ON THE SAME CALENDAR MONTHS and its change in points; and, per year and dimension, how much the composition moved:
    Σ |Δ share| / 2 (0 = the same composition, 1 = another one entirely). A year is read on its complete months, so
    the year before is read on those same months: a year still filling (January to September known) is compared
    with January to September of the year before, never with a whole year."""
    due_units, due_usd = configuration.pipeline_units_col, configuration.pipeline_usd_col
    complete = rows[rows[IS_COMPLETE]]
    coverage = complete.groupby(YEAR)[MONTH].agg(["min", "max", "nunique"])
    months_of_year = {year: set(months) for year, months in complete.groupby(YEAR)[MONTH_OF_YEAR].unique().items()}
    years = sorted(months_of_year)
    parts, changes = [], []
    for name, column in composition_dimensions(rows, configuration):
        summed = complete.groupby([YEAR, column]).agg(vence_usd=(due_usd, "sum"), vencen_unidades=(due_units, "sum")).reset_index()
        summed["valor"] = summed[column].astype(str)
        for position, year in enumerate(years):
            of_year = summed[summed[YEAR] == year].set_index("valor")
            total = of_year["vence_usd"].sum()
            share = of_year["vence_usd"] / total if total > 0 else of_year["vence_usd"] * 0.0
            before, months_before = None, ""
            if position:
                previous = years[position - 1]
                same_months = complete[(complete[YEAR] == previous) & complete[MONTH_OF_YEAR].isin(months_of_year[year])]
                if len(same_months):
                    by_value = same_months.groupby(same_months[column].astype(str))[due_usd].sum()
                    before = by_value / by_value.sum() if by_value.sum() > 0 else by_value * 0.0
                    months_before = f"{same_months[MONTH].min()}..{same_months[MONTH].max()}"
            for value in of_year.index:
                share_before = float(before.get(value, 0.0)) if before is not None else np.nan
                parts.append({"anio": int(year), "meses": f"{coverage.loc[year, 'min']}..{coverage.loc[year, 'max']}",
                              "n_meses": int(coverage.loc[year, "nunique"]), "meses_ano_anterior": months_before,
                              "dimension": name, "valor": value,
                              "vence_usd": float(of_year.loc[value, "vence_usd"]), "vencen_unidades": float(of_year.loc[value, "vencen_unidades"]),
                              "parte_usd": float(share[value]), "parte_usd_ano_anterior": share_before,
                              "cambio_pp": (float(share[value]) - share_before) * PERCENTAGE_POINTS if before is not None else np.nan})
            if before is not None:
                values = share.index.union(before.index)
                difference = share.reindex(values, fill_value=0.0) - before.reindex(values, fill_value=0.0)
                changes.append({"anio": int(year), "meses": f"{coverage.loc[year, 'min']}..{coverage.loc[year, 'max']}",
                                "meses_ano_anterior": months_before, "dimension": name, "valores": int((share > 0).sum()),
                                "cambio_composicion": float(difference.abs().sum() / 2),
                                "mayor_subida": str(difference.idxmax()), "mayor_bajada": str(difference.idxmin())})
    composition = pd.DataFrame(parts).sort_values(["dimension", "anio", "parte_usd"], ascending=[True, True, False]).reset_index(drop=True)
    change = (pd.DataFrame(changes).sort_values(["dimension", "anio"]).reset_index(drop=True) if changes
              else pd.DataFrame(columns=["anio", "meses", "meses_ano_anterior", "dimension", "valores", "cambio_composicion", "mayor_subida", "mayor_bajada"]))
    return composition, change


# ═══════════════════════════════════════════════════════════════════════════════════
# THE CUSTOMER STATES: BY MONTH, EARLY, AND AT THE SAME HORIZON A YEAR AGO
# ═══════════════════════════════════════════════════════════════════════════════════

def states_by_month(rows: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """One row per month and state: the units due in the state and their share of the month. In a closed month the
    state is final; in a future month it is what is seen so far (it grows until the month falls due)."""
    states = [state for state in configuration.structural_timevarying_dims if state in rows.columns]
    if not states:
        return pd.DataFrame()
    due_units = configuration.pipeline_units_col
    current = configuration.calendar_boundaries()["current"]
    totals = rows.groupby(MONTH)[due_units].sum()
    parts = []
    for state in states:
        in_state = rows[rows[state].isin(ACTIVE_FLAG_VALUES)].groupby(MONTH)[due_units].sum().reindex(totals.index, fill_value=0.0)
        part = pd.DataFrame({"mes": month_text(totals.index).to_numpy(), "anio": totals.index.year,
                             "estado_mes": np.where(totals.index < current, CLOSED, FUTURE), "estado": state,
                             "vencen_unidades": totals.to_numpy(), "en_estado_unidades": in_state.to_numpy()})
        part["parte"] = part["en_estado_unidades"] / part["vencen_unidades"].where(part["vencen_unidades"] > 0)
        part["parte_ano_anterior"] = a_year_before(pd.Series(part["parte"].to_numpy(), index=totals.index)).to_numpy()
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


def dated_state_columns(state: str, configuration: Config, from_k: int) -> list:
    return [f"{state}_month_{k}" for k in range(from_k, configuration.maturation_months + 1)]


def early_states(rows: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """One row per due month and dated state: the share of the units due that were ALREADY in the state in their
    first month (maturation_months or more months before due: the month of sale of a 1-year licence) and in their
    first two months. Read on the 1-year licences (when the extract says the term), so every cohort is compared with
    the same clock; a due month is listed when its first months are already seen (up to current + maturation_months − 1)."""
    dated = [state for state in configuration.maturation_dims if f"{state}_month_0" in rows.columns]
    if not dated:
        return pd.DataFrame()
    due_units = configuration.pipeline_units_col
    current = configuration.calendar_boundaries()["current"]
    last_k = configuration.maturation_months
    one_year = rows[rows[TERM_YEARS] == 1] if configuration.term_column else rows
    totals = one_year.groupby(MONTH)[due_units].sum()
    parts = []
    for state in dated:
        first_month = one_year.groupby(MONTH)[dated_state_columns(state, configuration, last_k)].sum().sum(axis=1)
        two_months = one_year.groupby(MONTH)[dated_state_columns(state, configuration, last_k - 1)].sum().sum(axis=1)
        final = one_year[one_year[state].isin(ACTIVE_FLAG_VALUES)].groupby(MONTH)[due_units].sum().reindex(totals.index, fill_value=0.0)
        part = pd.DataFrame({"mes": month_text(totals.index).to_numpy(), "anio": totals.index.year,
                             "estado_mes": np.where(totals.index < current, CLOSED, FUTURE), "estado": state,
                             "vencen_unidades_1y": totals.to_numpy(),
                             "en_estado_primer_mes": first_month.reindex(totals.index).fillna(0.0).to_numpy(),
                             "en_estado_dos_primeros_meses": two_months.reindex(totals.index).fillna(0.0).to_numpy(),
                             "en_estado_final": final.where(totals.index < current).to_numpy()}, index=totals.index)
        seen_first = part.index < current + last_k            # k = last_k is seen when month − last_k is closed
        seen_two = part.index < current + last_k - 1
        units = part["vencen_unidades_1y"].where(part["vencen_unidades_1y"] > 0)
        part["parte_primer_mes"] = (part["en_estado_primer_mes"] / units).where(seen_first)
        part["parte_dos_primeros_meses"] = (part["en_estado_dos_primeros_meses"] / units).where(seen_two)
        part["parte_final"] = part["en_estado_final"] / units
        part["parte_primer_mes_ano_anterior"] = a_year_before(part["parte_primer_mes"]).to_numpy()
        parts.append(part[seen_first].reset_index(drop=True))
    return pd.concat(parts, ignore_index=True)


def states_at_horizon(rows: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """One row per future month and dated state: the horizon (months from the last closed month), the share of the
    units due already in the state today, the share the cohort of the same month a year ago had at that same
    horizon, and the final share that cohort reached. The same clock on both: an early warning of a cohort filling
    its state faster or slower than the year before."""
    dated = [state for state in configuration.maturation_dims if f"{state}_month_0" in rows.columns]
    if not dated:
        return pd.DataFrame()
    due_units = configuration.pipeline_units_col
    current = configuration.calendar_boundaries()["current"]
    last_closed = current - 1
    totals = rows.groupby(MONTH)[due_units].sum()
    parts = []
    for state in dated:
        by_k = rows.groupby(MONTH)[dated_state_columns(state, configuration, 0)].sum()
        final = rows[rows[state].isin(ACTIVE_FLAG_VALUES)].groupby(MONTH)[due_units].sum().reindex(totals.index, fill_value=0.0)
        for month in totals.index[totals.index >= current]:
            horizon = month.ordinal - last_closed.ordinal
            if horizon > configuration.maturation_months:
                continue
            year_ago = month - MONTHS_PER_YEAR
            visible_columns = dated_state_columns(state, configuration, horizon)
            units_now, units_before = float(totals[month]), float(totals.get(year_ago, 0.0))
            parts.append({"mes": str(month), "estado": state, "horizonte_meses": int(horizon),
                          "vencen_unidades": units_now,
                          "parte_visible_hoy": float(by_k.loc[month, visible_columns].sum()) / units_now if units_now > 0 else np.nan,
                          "parte_visible_ano_anterior_mismo_horizonte": (float(by_k.loc[year_ago, visible_columns].sum()) / units_before
                                                                        if year_ago in by_k.index and units_before > 0 else np.nan),
                          "parte_final_ano_anterior": float(final.get(year_ago, np.nan)) / units_before if units_before > 0 else np.nan})
    return pd.DataFrame(parts)


# ═══════════════════════════════════════════════════════════════════════════════════
# THE OTHER UNIVERSE AND THE TERM TRANSITIONS
# ═══════════════════════════════════════════════════════════════════════════════════

def retail_to_subscription_by_month(time_series_rows: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """One row per closed month: the income and the units of the retail to subscription, against the year before."""
    if time_series_rows.empty:
        return pd.DataFrame()
    closed = time_series_rows[time_series_rows[IS_CLOSED]]
    summed = closed.groupby(MONTH).agg(ingresos_usd=(configuration.renewed_usd_col, "sum"),
                                        convertidas_unidades=(configuration.renewed_units_col, "sum"))
    summed = summed.reindex(full_month_range(summed.index), fill_value=0.0)
    table = pd.DataFrame({"mes": month_text(summed.index).to_numpy(), "anio": summed.index.year,
                          "ingresos_usd": summed["ingresos_usd"].to_numpy(), "convertidas_unidades": summed["convertidas_unidades"].to_numpy()})
    table["ingresos_usd_ano_anterior"] = a_year_before(summed["ingresos_usd"]).to_numpy()
    table["variacion_usd_vs_ano_anterior"] = change_against(table["ingresos_usd"], table["ingresos_usd_ano_anterior"])
    return table


def term_transitions_by_year(rows: pd.DataFrame, configuration: Config) -> pd.DataFrame:
    """One row per year and origin term (closed months): the renewed units and the share that went to a 1, 2 or 3-year
    licence, in units and in USD."""
    columns = transition_columns(configuration)
    if not columns or not all(units in rows.columns and usd in rows.columns for _, _, units, usd in columns):
        return pd.DataFrame()
    closed = rows[rows[IS_CLOSED]]
    measures = {"renovadas_unidades": (configuration.renewed_units_col, "sum"), "renovado_usd": (configuration.renewed_usd_col, "sum")}
    for short_name, _, units_column, usd_column in columns:
        measures[f"unidades_a_{short_name}"] = (units_column, "sum")
        measures[f"usd_a_{short_name}"] = (usd_column, "sum")
    summed = closed.groupby([YEAR, TERM_YEARS]).agg(**measures).reset_index()
    summed = summed.rename(columns={YEAR: "anio", TERM_YEARS: "plazo_origen_anios"})
    known_units = summed[[f"unidades_a_{short_name}" for short_name, _, _, _ in columns]].sum(axis=1)
    for short_name, _, _, _ in columns:
        summed[f"parte_a_{short_name}"] = summed[f"unidades_a_{short_name}"] / known_units.where(known_units > 0)
    summed["parte_destino_conocido"] = known_units / summed["renovadas_unidades"].where(summed["renovadas_unidades"] > 0)
    return summed


# ═══════════════════════════════════════════════════════════════════════════════════
# THE TRENDS: ONE ROW PER KPI
# ═══════════════════════════════════════════════════════════════════════════════════

def kpi_series(tables: dict, configuration: Config) -> list:
    """(kpi, what it is, the monthly series indexed by Period, in points?) of every KPI whose trend is measured."""
    series = []
    monthly = tables.get("pipeline_mes")
    if monthly is not None and len(monthly):
        index = pd.PeriodIndex(monthly["mes"], freq="M")
        known = monthly["completa"] == 1
        series.append(("vence_usd", "USD que vence al mes (meses cerrados y futuros completos)",
                       pd.Series(monthly["vence_usd"].where(known).to_numpy(), index=index), False))
        series.append(("vencen_unidades", "unidades que vencen al mes (meses cerrados y futuros completos)",
                       pd.Series(monthly["vencen_unidades"].where(known).to_numpy(), index=index), False))
        series.append(("tasa_unidades", "tasa de renovación en unidades (meses cerrados)",
                       pd.Series(monthly["tasa_unidades"].to_numpy(), index=index), True))
        series.append(("tasa_usd", "tasa de renovación en USD (meses cerrados)",
                       pd.Series(monthly["tasa_usd"].to_numpy(), index=index), True))
        series.append(("renovado_usd", "USD renovado al mes (meses cerrados)",
                       pd.Series(monthly["renovado_usd"].to_numpy(), index=index), False))
    uplift = tables.get("uplift_mes")
    if uplift is not None and len(uplift):
        index = pd.PeriodIndex(uplift["mes"], freq="M")
        series.append(("uplift", "revalorización de lo renovado (meses cerrados)", pd.Series(uplift["uplift"].to_numpy(), index=index), False))
        if uplift["uplift_aislado"].notna().any():
            series.append(("uplift_aislado", "revalorización de las renovaciones aisladas (sin descuentos de retención)",
                           pd.Series(uplift["uplift_aislado"].to_numpy(), index=index), False))
    terms = tables.get("plazo_mes")
    if terms is not None and len(terms):
        one_year = terms[(terms["plazo_anios"] == 1) & (terms["completa"] == 1)]
        series.append(("parte_1_anio", "parte del USD que vence en licencias de 1 año",
                       pd.Series(one_year["parte_usd"].to_numpy(), index=pd.PeriodIndex(one_year["mes"], freq="M")), True))
    acquisition = tables.get("adquisicion_mes")
    if acquisition is not None and len(acquisition):
        one_year = acquisition[(acquisition["plazo_anios"] == 1) & (acquisition["observable"] == 1)]
        index = pd.PeriodIndex(one_year["mes_venta"], freq="M")
        series.append(("adquisicion_unidades", "unidades adquiridas al mes en licencias de 1 año (por mes de venta)", pd.Series(one_year["vendidas_unidades"].to_numpy(), index=index), False))
        series.append(("adquisicion_usd", "USD de las adquisiciones de 1 año (lo que vencerá), por mes de venta", pd.Series(one_year["vendido_usd"].to_numpy(), index=index), False))
    states = tables.get("estados_mes")
    if states is not None and len(states):
        for state, of_state in states[states["estado_mes"] == CLOSED].groupby("estado"):
            series.append((f"{state}_parte", f"parte de las unidades que vencen en {state} (meses cerrados, estado final)",
                           pd.Series(of_state["parte"].to_numpy(), index=pd.PeriodIndex(of_state["mes"], freq="M")), True))
    early = tables.get("estados_tempranos")
    if early is not None and len(early):
        for state, of_state in early.groupby("estado"):
            series.append((f"{state}_primer_mes", f"parte de las licencias de 1 año ya en {state} en su primer mes",
                           pd.Series(of_state["parte_primer_mes"].to_numpy(), index=pd.PeriodIndex(of_state["mes"], freq="M")), True))
    retail = tables.get("retail_to_subscription")
    if retail is not None and len(retail):
        series.append(("retail_to_subscription_usd", "ingresos del retail to subscription al mes",
                       pd.Series(retail["ingresos_usd"].to_numpy(), index=pd.PeriodIndex(retail["mes"], freq="M")), False))
    return series


def trends_table(series: list, configuration: Config) -> tuple:
    """One row per KPI with its trend (trend_of), and the fitted lines and month effects for the charts."""
    rows, fits = [], {}
    for kpi, description, monthly, in_points in series:
        trend = trend_of(monthly, configuration, in_points=in_points)
        fits[kpi] = {"fitted": trend.pop("_fitted"), "month_effects": trend.pop("_month_effects"), "series": monthly, "in_points": in_points}
        rows.append({"kpi": kpi, "que_es": description, "en_puntos": int(in_points), **trend})
    columns = ["kpi", "que_es", "en_puntos", "meses", "primer_mes", "ultimo_mes", "media", "media_ultimos_12", "media_12_anteriores",
               "variacion_12m", "pendiente_anual", "pendiente_relativa_anual", "p_valor_tendencia", "tendencia", "estacional",
               "p_valor_mes", "amplitud_estacional", "meses_alto", "meses_bajo"]
    return pd.DataFrame(rows, columns=columns), fits


# ═══════════════════════════════════════════════════════════════════════════════════
# THE CHARTS
# ═══════════════════════════════════════════════════════════════════════════════════

def titles(figure, title: str, subtitle: str = "") -> None:
    """The title and the subtitle of a chart, placed by inches from the top whatever the height of the figure (the
    tallest charts have several panels). The subtitle is not wrapped: a wrapped text with a "$" in it is parsed as
    maths by matplotlib whatever text.parse_math says."""
    height = figure.get_size_inches()[1]
    figure.suptitle(title, x=0.01, y=0.99, ha="left", va="top", fontsize=13, fontweight="bold", color=INK)
    if subtitle:
        figure.text(0.01, 0.99 - 0.36 / height, subtitle, ha="left", va="top", fontsize=9.5, color=INK_SECONDARY)
    figure.titles_height_inches = 0.85 if subtitle else 0.55


def save(figure, path: str, top: float = None) -> str:
    """The PNG, with the axes laid out below the titles (graficos.save, the top computed from the height)."""
    height = figure.get_size_inches()[1]
    return save_png(figure, path, top=1 - getattr(figure, "titles_height_inches", 0.55) / height)


def month_labels(months: pd.PeriodIndex) -> list:
    """A label per month: the year at every January, blank otherwise (the axis stays readable)."""
    return [str(month.year) if month.month == 1 else "" for month in months]


def draw_pipeline_by_month(monthly: pd.DataFrame, yearly: pd.DataFrame, path: str, configuration: Config) -> str:
    months = pd.PeriodIndex(monthly["mes"], freq="M")
    positions = np.arange(len(months))
    closed = monthly["estado"] == CLOSED
    complete = (monthly["completa"] == 1) & ~closed
    figure, axes = new_figure(14, 9, 2, 1, gridspec_kw={"height_ratios": [3, 2]})
    axis = axes[0]
    axis.bar(positions[closed], monthly.loc[closed, "vence_usd"], color=BLUE, label="vence (meses cerrados)")
    axis.bar(positions[complete], monthly.loc[complete, "vence_usd"], color=ORANGE, label="vence (futuro, pipeline completa)")
    incomplete = ~closed & ~complete
    axis.bar(positions[incomplete], monthly.loc[incomplete, "vence_usd"], color=NEUTRAL_FILL, hatch="//", edgecolor=INK_MUTED,
             label="vence (futuro, aún se llena)")
    axis.plot(positions[closed], monthly.loc[closed, "renovado_usd"], color=INK, linewidth=1.4, label="renovado real")
    axis.plot(positions, monthly["vence_usd_ano_anterior"], color=INK_MUTED, linewidth=1.2, linestyle="--", label="vence, mismo mes del año anterior")
    axis.set_xticks(positions)
    axis.set_xticklabels(month_labels(months))
    axis.set_xlim(-0.6, len(months) - 0.4)
    axis.set_ylim(0, float(monthly["vence_usd"].max()) * 1.3)          # room for the legend above the bars
    axis.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda value, _: money_label(value)))
    axis.legend(loc="upper left", fontsize=8.5, frameon=False, ncol=3)
    axis.set_title("La pipeline mes a mes: lo que vence, lo que renovó y el mismo mes del año anterior", fontsize=10.5, loc="left", color=INK_SECONDARY)
    axis = axes[1]
    change = monthly["variacion_usd_vs_ano_anterior"] * PERCENTAGE_POINTS
    shown = monthly["completa"] == 1
    colours = np.where(change >= 0, AQUA, ORANGE)
    axis.bar(positions[shown], change[shown], color=colours[shown])
    axis.axhline(0, color=INK_MUTED, linewidth=0.8)
    axis.set_xticks(positions)
    axis.set_xticklabels(month_labels(months))
    axis.set_xlim(-0.6, len(months) - 0.4)
    axis.set_ylabel("% frente al mismo mes del año anterior")
    axis.set_title("Crecimiento del USD que vence frente al mismo mes del año anterior (meses cerrados y futuros completos)",
                   fontsize=10.5, loc="left", color=INK_SECONDARY)
    current = str(configuration.calendar_boundaries()["current"])
    latest = yearly.iloc[-1]
    subtitle = (f"mes en curso {current} · " + " · ".join(f"{int(row['anio'])}: {money_label(row['vence_usd'])}"
                                                         + (f" ({row['crecimiento_usd_vs_ano_anterior']:+.1%} en meses comparables)"
                                                            if np.isfinite(row['crecimiento_usd_vs_ano_anterior']) else "")
                                                         for _, row in yearly.tail(3).iterrows()))
    titles(figure, "01 · La pipeline: cuánto vence cada mes y si crece frente al año anterior", subtitle)
    return save(figure, path, top=0.9)


def draw_rhythm(monthly: pd.DataFrame, path: str, column: str, title: str, label: str, money: bool = True) -> str:
    """The calendar-month profile of every year: one line per year (the known part of the next year dashed)."""
    figure, axis = new_figure(12, 5.5)
    years = sorted(monthly["anio"].unique())
    for position, year in enumerate(years):
        of_year = monthly[(monthly["anio"] == year) & (monthly["completa"] == 1)]
        if of_year.empty:
            continue
        colour = YEAR_COLOURS[max(0, len(YEAR_COLOURS) - len(years) + position)] if len(years) <= len(YEAR_COLOURS) else YEAR_COLOURS[min(position, len(YEAR_COLOURS) - 1)]
        is_future = (of_year["estado"] == FUTURE).any()
        axis.plot(of_year["mes_del_anio"], of_year[column], color=colour, linewidth=2 if position >= len(years) - 2 else 1.4,
                  linestyle="--" if is_future else "-", marker="o", markersize=3, label=f"{year}" + (" (lo ya conocido)" if is_future else ""))
    axis.set_xticks(range(1, 13))
    axis.set_xticklabels(MONTH_NAMES)
    if money:
        axis.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda value, _: money_label(value)))
    axis.set_ylabel(label)
    axis.legend(loc="best", fontsize=8.5, frameon=False)
    titles(figure, title, "el mismo mes de cada año, uno sobre otro: la estacionalidad y el crecimiento se ven a la vez")
    return save(figure, path)


def draw_terms(terms: pd.DataFrame, path: str) -> str:
    wide = terms.pivot_table(index="mes", columns="plazo_anios", values="parte_usd", fill_value=0.0)
    months = pd.PeriodIndex(wide.index, freq="M")
    positions = np.arange(len(months))
    figure, axis = new_figure(12, 5)
    bottom = np.zeros(len(months))
    colours = [BLUE, AQUA, VIOLET, ORANGE]
    for position, term in enumerate(wide.columns):
        axis.bar(positions, wide[term] * PERCENTAGE_POINTS, bottom=bottom, color=colours[position % len(colours)], width=1.0, label=f"{term} año(s)")
        bottom += wide[term].to_numpy() * PERCENTAGE_POINTS
    complete_until = terms.loc[terms["completa"] == 1, "mes"].max()
    boundary = list(wide.index).index(complete_until) if complete_until in wide.index else len(months) - 1
    axis.axvline(boundary + 0.5, color=INK, linewidth=1, linestyle=":")
    axis.text(boundary + 0.7, 95, "aún se llena →", fontsize=8.5, color=INK_SECONDARY)
    axis.set_xticks(positions)
    axis.set_xticklabels(month_labels(months))
    axis.set_ylim(0, 100)
    axis.set_ylabel("% del USD que vence")
    axis.legend(loc="lower left", fontsize=8.5, frameon=False, ncol=3)
    titles(figure, "03 · El plazo de las licencias que vencen: la parte de 1, 2 y 3 años mes a mes",
           "los meses que aún se llenan tienen menos licencias de 1 año de las que tendrán (sus ventas y renovaciones no han llegado)")
    return save(figure, path)


def draw_rate(rate: pd.DataFrame, fits: dict, path: str, configuration: Config) -> str:
    total = rate[rate["dimension"] == TOTAL].sort_values("mes")
    months = pd.PeriodIndex(total["mes"], freq="M")
    positions = np.arange(len(months))
    figure, axes = new_figure(13, 9, 2, 1)
    axis = axes[0]
    axis.fill_between(positions, total["tasa_binomial_baja"] * PERCENTAGE_POINTS, total["tasa_binomial_alta"] * PERCENTAGE_POINTS,
                      color=BLUE, alpha=0.12, label="banda binomial (90 %)")
    axis.plot(positions, total["tasa_unidades"] * PERCENTAGE_POINTS, color=BLUE, linewidth=1.8, marker="o", markersize=3, label="tasa en unidades")
    axis.plot(positions, total["tasa_usd"] * PERCENTAGE_POINTS, color=AQUA, linewidth=1.2, label="tasa en USD (renovado / vence)")
    fit = fits.get("tasa_unidades", {}).get("fitted")
    if fit is not None and len(fit):
        fitted_positions = [list(months).index(month) for month in fit.index if month in set(months)]
        axis.plot(fitted_positions, fit.to_numpy()[:len(fitted_positions)] * PERCENTAGE_POINTS, color=ORANGE, linewidth=1.4, linestyle="--", label="recta de regresión (unidades)")
    axis.set_xticks(positions)
    axis.set_xticklabels(month_labels(months))
    axis.set_ylabel("%")
    axis.legend(loc="best", fontsize=8.5, frameon=False, ncol=2)
    axis.set_title("La tasa real de cada mes cerrado, su banda binomial y su recta", fontsize=10.5, loc="left", color=INK_SECONDARY)
    axis = axes[1]
    preferred = [region_columns_of(configuration)[0]] + [name for name, _ in term_dimension(configuration)] + ["origen"]
    present = [name for name in rate["dimension"].unique() if name != TOTAL]
    dimensions = [name for name in preferred if name in present] + [name for name in present if name not in preferred]
    drawn = 0
    if dimensions:
        first = rate[rate["dimension"] == dimensions[0]]
        biggest = first.groupby("valor")["vencen_unidades"].sum().sort_values(ascending=False).head(6).index
        colours = [BLUE, ORANGE, AQUA, VIOLET, INK_MUTED, "#b08968"]
        for position, value in enumerate(biggest):
            of_value = first[first["valor"] == value].sort_values("mes")
            value_positions = [list(months).index(pd.Period(month, freq="M")) for month in of_value["mes"]]
            axis.plot(value_positions, of_value["tasa_unidades"] * PERCENTAGE_POINTS, color=colours[position % len(colours)], linewidth=1.3, label=str(value))
            drawn += 1
        axis.set_title(f"La tasa en unidades por {dimensions[0]} (los {drawn} mayores por unidades)", fontsize=10.5, loc="left", color=INK_SECONDARY)
        axis.legend(loc="best", fontsize=8.5, frameon=False, ncol=3)
    axis.set_xticks(positions)
    axis.set_xticklabels(month_labels(months))
    axis.set_ylabel("%")
    last_12 = total.tail(MONTHS_PER_YEAR)
    before_12 = total.iloc[-2 * MONTHS_PER_YEAR:-MONTHS_PER_YEAR]
    subtitle = (f"últimos 12 meses cerrados: {last_12['renovadas_unidades'].sum() / last_12['vencen_unidades'].sum():.1%} en unidades"
                + (f" · los 12 anteriores: {before_12['renovadas_unidades'].sum() / before_12['vencen_unidades'].sum():.1%}" if len(before_12) == MONTHS_PER_YEAR else ""))
    titles(figure, "04 · La tasa de renovación real: cómo ha evolucionado", subtitle)
    return save(figure, path, top=0.92)


def draw_month_against_month(comparison: pd.DataFrame, dimensions: list, path: str, top_values: int) -> str:
    """The bridge of the renewed USD of the last closed month against the same month a year before (pipeline, rate,
    uplift), and where the differences are by dimension (the values that move the most)."""
    last = comparison[comparison["comparacion"] == LAST_MONTH]
    total = last[last["dimension"] == TOTAL].iloc[0]
    figure, axes = new_figure(14, 5.2 + 4.6 * len(dimensions), 1 + len(dimensions), 1, squeeze=False,
                              gridspec_kw={"height_ratios": [5.2] + [4.6] * len(dimensions)})
    axis = axes[0][0]
    steps = [("renovado " + total["mes_antes"], total["renovado_usd_antes"], INK_MUTED),
             ("efecto pipeline", total["efecto_pipeline_usd"], BLUE), ("efecto tasa", total["efecto_tasa_usd"], ORANGE),
             ("efecto uplift", total["efecto_uplift_usd"], AQUA), ("renovado " + total["mes_hoy"], total["renovado_usd_hoy"], INK)]
    running, levels = 0.0, []
    for position, (label, value, colour) in enumerate(steps):
        if position in (0, len(steps) - 1):
            axis.bar(position, value, color=colour, width=0.6)
            axis.text(position, value, money_label(value), ha="center", va="bottom", fontsize=9, color=INK)
            running = value
        else:
            axis.bar(position, value, bottom=running, color=colour, width=0.6)
            axis.text(position, running + max(value, 0), f"{'+' if value >= 0 else '−'}{money_label(abs(value))}", ha="center", va="bottom", fontsize=9, color=INK)
            running += value
        levels += [running, running - (value if 0 < position < len(steps) - 1 else 0)]
    axis.set_xticks(range(len(steps)))
    axis.set_xticklabels([label for label, _, _ in steps], fontsize=9)
    # the axis starts near the smaller total, so the three effects are seen (from 0 they would be a hair on the bars)
    low, high = min(levels), max(levels)
    axis.set_ylim(max(0.0, low - (high - low) * 1.2 - abs(high) * 0.02), high + (high - low) * 0.5 + abs(high) * 0.02)
    axis.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda value, _: money_label(value)))
    axis.set_title(f"De lo renovado en {total['mes_antes']} a lo renovado en {total['mes_hoy']}: vence {money_label(total['vence_usd_antes'])} → "
                   f"{money_label(total['vence_usd_hoy'])} · tasa {total['tasa_unidades_antes']:.1%} → {total['tasa_unidades_hoy']:.1%}"
                   + (f" · uplift {total['uplift_antes']:.3f} → {total['uplift_hoy']:.3f}" if np.isfinite(total["uplift_hoy"]) else ""),
                   fontsize=10.5, loc="left", color=INK_SECONDARY)
    for row_position, dimension in enumerate(dimensions, start=1):
        axis = axes[row_position][0]
        of_dimension = last[last["dimension"] == dimension].copy()
        of_dimension["_peso"] = of_dimension["renovado_usd_diferencia"].abs()
        of_dimension = of_dimension.sort_values("_peso", ascending=False).head(top_values).iloc[::-1]
        positions = np.arange(len(of_dimension))
        axis.barh(positions - 0.25, of_dimension["efecto_pipeline_usd"], 0.25, color=BLUE, label="efecto pipeline")
        axis.barh(positions, of_dimension["efecto_tasa_usd"], 0.25, color=ORANGE, label="efecto tasa")
        axis.barh(positions + 0.25, of_dimension["efecto_uplift_usd"], 0.25, color=AQUA, label="efecto uplift")
        axis.plot(of_dimension["renovado_usd_diferencia"], positions, "o", color=INK, markersize=5, label="diferencia de lo renovado")
        axis.axvline(0, color=INK_MUTED, linewidth=0.8)
        axis.set_yticks(positions)
        axis.set_yticklabels([f"{value}  ({money_label(before)} → {money_label(now)}, tasa {points(diff, 1)})"
                              for value, before, now, diff in zip(of_dimension["valor"], of_dimension["renovado_usd_antes"],
                                                                  of_dimension["renovado_usd_hoy"], of_dimension["tasa_unidades_diferencia_pp"])], fontsize=8.5)
        axis.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda value, _: money_label(value)))
        axis.grid(True, axis="x", color=GRID, linewidth=0.8)
        axis.grid(False, axis="y")
        if row_position == 1:
            axis.legend(loc="lower left", bbox_to_anchor=(1.01, 0.0), fontsize=8, frameon=False)
        axis.set_title(f"por {dimension}: los {len(of_dimension)} valores que más mueven lo renovado (antes → hoy, y la tasa en pp)",
                       fontsize=10.5, loc="left", color=INK_SECONDARY)
    titles(figure, f"02b · {total['mes_hoy']} frente a {total['mes_antes']}: dónde están las diferencias",
           "lo renovado cambia por tres cosas: venció más o menos (pipeline), renovó más o menos (tasa) y renovó a otro precio (uplift)")
    return save(figure, path, top=0.94 if len(dimensions) > 1 else 0.88)


def draw_uplift(uplift: pd.DataFrame, increases: pd.DataFrame, fits: dict, path: str) -> str:
    months = pd.PeriodIndex(uplift["mes"], freq="M")
    positions = np.arange(len(months))
    figure, axes = new_figure(13, 8.5, 2, 1, gridspec_kw={"height_ratios": [3, 1.6]})
    axis = axes[0]
    axis.plot(positions, uplift["uplift"], color=BLUE, linewidth=1.8, marker="o", markersize=3, label="uplift de todo lo renovado")
    if uplift["uplift_aislado"].notna().any():
        axis.plot(positions, uplift["uplift_aislado"], color=VIOLET, linewidth=1.3, label="uplift de las renovaciones aisladas (sin descuentos de retención)")
    fit = fits.get("uplift", {}).get("fitted")
    if fit is not None and len(fit):
        fitted_positions = [list(months).index(month) for month in fit.index if month in set(months)]
        axis.plot(fitted_positions, fit.to_numpy()[:len(fitted_positions)], color=ORANGE, linewidth=1.3, linestyle="--", label="recta de regresión")
    axis.axhline(1.0, color=INK_MUTED, linewidth=0.8)
    axis.set_xticks(positions)
    axis.set_xticklabels(month_labels(months))
    axis.set_ylabel("renovado / lo que valía")
    axis.legend(loc="best", fontsize=8.5, frameon=False)
    axis.set_title("La revalorización de cada mes cerrado", fontsize=10.5, loc="left", color=INK_SECONDARY)
    axis = axes[1]
    axis.bar(positions, uplift["parte_usd_en_subida"] * PERCENTAGE_POINTS, color=ORANGE, width=1.0, label="% del USD renovado dentro del ciclo de una subida")
    starts = uplift["subidas_que_empiezan"].to_numpy()
    for position in positions[starts > 0]:
        axis.annotate(f"+{int(starts[position])}", (position, uplift.loc[position, 'parte_usd_en_subida'] * PERCENTAGE_POINTS + 2),
                      ha="center", fontsize=7.5, color=INK_SECONDARY)
    axis.set_xticks(positions)
    axis.set_xticklabels(month_labels(months))
    axis.set_ylim(0, 105)
    axis.set_ylabel("%")
    axis.legend(loc="upper left", fontsize=8.5, frameon=False)
    axis.set_title("Las subidas de precio detectadas: cuánto de lo renovado está en el ciclo de una (+n: subidas que empiezan ese mes)",
                   fontsize=10.5, loc="left", color=INK_SECONDARY)
    titles(figure, "05 · La revalorización y las subidas de precio que ha habido",
           f"{len(increases)} subidas detectadas en la historia" if increases is not None else "")
    return save(figure, path, top=0.92)


def draw_acquisition(acquisition: pd.DataFrame, fits: dict, path: str) -> str:
    one_year = acquisition[(acquisition["plazo_anios"] == 1) & (acquisition["observable"] == 1)].sort_values("mes_venta")
    months = pd.PeriodIndex(one_year["mes_venta"], freq="M")
    positions = np.arange(len(months))
    figure, axes = new_figure(13, 9, 2, 1)
    axis = axes[0]
    axis.bar(positions, one_year["vendidas_unidades"], color=BLUE, width=1.0, label="unidades vendidas (licencias de 1 año)")
    axis.plot(positions, one_year["vendidas_unidades_ano_anterior"], color=INK_MUTED, linewidth=1.2, linestyle="--", label="mismo mes del año anterior")
    fit = fits.get("adquisicion_unidades", {}).get("fitted")
    if fit is not None and len(fit):
        fitted_positions = [list(months).index(month) for month in fit.index if month in set(months)]
        axis.plot(fitted_positions, fit.to_numpy()[:len(fitted_positions)], color=ORANGE, linewidth=1.4, linestyle="--", label="recta de regresión")
    axis.set_xticks(positions)
    axis.set_xticklabels(month_labels(months))
    axis.set_ylabel("unidades vendidas")
    axis.set_ylim(0, float(one_year["vendidas_unidades"].max()) * 1.25)
    axis.legend(loc="upper left", fontsize=8.5, frameon=False, ncol=3)
    axis.set_title("Las adquisiciones de 1 año por mes de venta (el mes en que se vendieron: su vencimiento menos 12 meses)", fontsize=10.5, loc="left", color=INK_SECONDARY)
    axis = axes[1]
    years = sorted(one_year["anio_venta"].unique())
    for position, year in enumerate(years):
        of_year = one_year[one_year["anio_venta"] == year]
        colour = YEAR_COLOURS[max(0, len(YEAR_COLOURS) - len(years) + position)] if len(years) <= len(YEAR_COLOURS) else YEAR_COLOURS[min(position, len(YEAR_COLOURS) - 1)]
        axis.plot(of_year["mes_del_anio"], of_year["vendidas_unidades"], color=colour, marker="o", markersize=3,
                  linewidth=2 if position >= len(years) - 2 else 1.3, label=str(year))
    axis.set_xticks(range(1, 13))
    axis.set_xticklabels(MONTH_NAMES)
    axis.set_ylabel("unidades vendidas")
    axis.legend(loc="best", fontsize=8.5, frameon=False, ncol=3)
    axis.set_title("El ritmo de la adquisición: el mismo mes de cada año", fontsize=10.5, loc="left", color=INK_SECONDARY)
    titles(figure, "06 · La adquisición: cuánto se vende cada mes y su tendencia",
           "licencias de 1 año, en los meses de venta observables (las de 2 y 3 años vencen fuera del extracto en los meses recientes: tabla)")
    return save(figure, path)


def draw_composition(composition: pd.DataFrame, change: pd.DataFrame, dimensions: list, path: str, top_values: int) -> str:
    figure, axes = new_figure(14, 4.8 * len(dimensions), len(dimensions), 1, squeeze=False)
    colours = [BLUE, ORANGE, AQUA, VIOLET, "#b08968", "#5c8ca6", "#c97b9c", INK_MUTED]
    for row_position, dimension in enumerate(dimensions):
        axis = axes[row_position][0]
        of_dimension = composition[composition["dimension"] == dimension]
        if of_dimension.empty:
            continue
        ranking = of_dimension.groupby("valor")["vence_usd"].sum().sort_values(ascending=False)
        kept = list(ranking.head(top_values).index)
        of_dimension = of_dimension.assign(valor_dibujado=np.where(of_dimension["valor"].isin(kept), of_dimension["valor"], OTHERS))
        wide = of_dimension.pivot_table(index="anio", columns="valor_dibujado", values="parte_usd", aggfunc="sum", fill_value=0.0)
        wide = wide[[value for value in kept if value in wide.columns] + ([OTHERS] if OTHERS in wide.columns else [])]
        years = list(wide.index)
        positions = np.arange(len(years))
        bottom = np.zeros(len(years))
        for value_position, value in enumerate(wide.columns):
            share = wide[value].to_numpy() * PERCENTAGE_POINTS
            axis.bar(positions, share, bottom=bottom, color=colours[value_position % len(colours)], width=0.7, label=str(value))
            for year_position, (height, base) in enumerate(zip(share, bottom)):
                if height >= 6:
                    axis.text(year_position, base + height / 2, f"{height:.0f} %", ha="center", va="center", fontsize=8, color="white")
            bottom += share
        labels = []
        for year in years:
            of_year = of_dimension[of_dimension["anio"] == year].iloc[0]
            moved = change[(change["dimension"] == dimension) & (change["anio"] == year)]
            labels.append(f"{year}\n{of_year['meses']}" + (f"\ncambio {moved['cambio_composicion'].iloc[0]:.1%}" if len(moved) else ""))
        axis.set_xticks(positions)
        axis.set_xticklabels(labels, fontsize=8.5)
        axis.set_ylim(0, 100)
        axis.set_ylabel("% del USD que vence")
        axis.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=8.5, frameon=False)
        axis.set_title(f"por {dimension}", fontsize=10.5, loc="left", color=INK_SECONDARY)
    titles(figure, "07 · La composición de la pipeline, año a año: ¿está cambiando?",
           "cada año con los meses que cubre (los futuros, solo los meses completos); 'cambio' = Σ |Δ parte| / 2 frente al año anterior")
    return save(figure, path, top=0.95 if len(dimensions) > 2 else 0.88)


def draw_states(states: pd.DataFrame, early: pd.DataFrame, horizon: pd.DataFrame, fits: dict, path: str) -> str:
    panels = 1 + int(len(early) > 0) + int(len(horizon) > 0)
    figure, axes = new_figure(13, 4.6 * panels, panels, 1, squeeze=False)
    colours = {state: colour for state, colour in zip(sorted(states["estado"].unique()), [ORANGE, VIOLET, AQUA, BLUE, INK_MUTED])}
    axis = axes[0][0]
    months = pd.PeriodIndex(sorted(states["mes"].unique()), freq="M")
    positions = {str(month): position for position, month in enumerate(months)}
    for state, of_state in states.groupby("estado"):
        of_state = of_state.sort_values("mes")
        closed = of_state[of_state["estado_mes"] == CLOSED]
        future = of_state[of_state["estado_mes"] == FUTURE]
        axis.plot([positions[month] for month in closed["mes"]], closed["parte"] * PERCENTAGE_POINTS, color=colours[state], linewidth=1.6, label=f"{state} (cerrado: estado final)")
        axis.plot([positions[month] for month in future["mes"]], future["parte"] * PERCENTAGE_POINTS, color=colours[state], linewidth=1.6, linestyle=":", label=f"{state} (futuro: lo visto hasta hoy)")
    axis.set_xticks(range(len(months)))
    axis.set_xticklabels(month_labels(months))
    axis.set_ylabel("% de las unidades que vencen")
    axis.legend(loc="best", fontsize=8, frameon=False, ncol=2)
    axis.set_title("Los estados del cliente mes a mes: final en los meses cerrados, lo visto hasta hoy en los futuros", fontsize=10.5, loc="left", color=INK_SECONDARY)
    next_panel = 1
    if len(early):
        axis = axes[next_panel][0]
        next_panel += 1
        for state, of_state in early.groupby("estado"):
            of_state = of_state.sort_values("mes")
            early_positions = [positions.get(month, np.nan) for month in of_state["mes"]]
            axis.plot(early_positions, of_state["parte_primer_mes"] * PERCENTAGE_POINTS, color=colours.get(state, BLUE), linewidth=1.6, marker="o", markersize=3, label=f"{state} ya en el primer mes")
            axis.plot(early_positions, of_state["parte_dos_primeros_meses"] * PERCENTAGE_POINTS, color=colours.get(state, BLUE), linewidth=1.1, linestyle="--", label=f"{state} en los dos primeros meses")
            fit = fits.get(f"{state}_primer_mes", {}).get("fitted")
            if fit is not None and len(fit):
                axis.plot([positions.get(str(month), np.nan) for month in fit.index], fit.to_numpy() * PERCENTAGE_POINTS, color=ORANGE, linewidth=1.2, linestyle="--", label="recta de regresión")
        axis.set_xticks(range(len(months)))
        axis.set_xticklabels(month_labels(months))
        axis.set_ylabel("% de las licencias de 1 año")
        axis.legend(loc="best", fontsize=8, frameon=False, ncol=2)
        axis.set_title("El estado temprano: la parte de cada cohorte (por mes de vencimiento) ya en el estado en su primer mes de vida",
                       fontsize=10.5, loc="left", color=INK_SECONDARY)
    if len(horizon):
        axis = axes[next_panel][0]
        for state, of_state in horizon.groupby("estado"):
            of_state = of_state.sort_values("mes")
            horizon_positions = np.arange(len(of_state))
            width = 0.27
            axis.bar(horizon_positions - width, of_state["parte_visible_hoy"] * PERCENTAGE_POINTS, width, color=colours.get(state, BLUE), label=f"{state}: visible hoy")
            axis.bar(horizon_positions, of_state["parte_visible_ano_anterior_mismo_horizonte"] * PERCENTAGE_POINTS, width, color=NEUTRAL_FILL, label="hace un año, al mismo horizonte")
            axis.bar(horizon_positions + width, of_state["parte_final_ano_anterior"] * PERCENTAGE_POINTS, width, color=INK_MUTED, label="hace un año, al vencer (final)")
            axis.set_xticks(horizon_positions)
            axis.set_xticklabels([f"{month}\nh={h}" for month, h in zip(of_state["mes"], of_state["horizonte_meses"])], fontsize=8)
            break                                   # one dated state per panel keeps it readable: the table has every state
        axis.set_ylabel("% de las unidades que vencen")
        axis.legend(loc="best", fontsize=8, frameon=False, ncol=3)
        axis.set_title("Los meses que vienen: lo visible hoy frente a la cohorte de hace un año al mismo horizonte (h = meses hasta vencer)",
                       fontsize=10.5, loc="left", color=INK_SECONDARY)
    titles(figure, "08 · Los estados del cliente: cuánto hay, cuánto aparece pronto y cómo van las cohortes que vienen", "")
    return save(figure, path, top=0.95 if panels > 1 else 0.88)


def draw_retail_to_subscription(retail: pd.DataFrame, fits: dict, path: str) -> str:
    months = pd.PeriodIndex(retail["mes"], freq="M")
    positions = np.arange(len(months))
    figure, axis = new_figure(12, 5)
    axis.bar(positions, retail["ingresos_usd"], color=VIOLET, width=1.0, label="ingresos del mes")
    axis.plot(positions, retail["ingresos_usd_ano_anterior"], color=INK_MUTED, linewidth=1.2, linestyle="--", label="mismo mes del año anterior")
    fit = fits.get("retail_to_subscription_usd", {}).get("fitted")
    if fit is not None and len(fit):
        axis.plot([list(months).index(month) for month in fit.index if month in set(months)], fit.to_numpy(), color=ORANGE, linewidth=1.3, linestyle="--", label="recta de regresión")
    axis.set_xticks(positions)
    axis.set_xticklabels(month_labels(months))
    axis.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda value, _: money_label(value)))
    axis.legend(loc="best", fontsize=8.5, frameon=False)
    titles(figure, "09 · El retail to subscription: los ingresos de cada mes cerrado", "el otro universo del extracto: se proyecta aparte (paso 6.1)")
    return save(figure, path)


def draw_the_charts(tables: dict, fits: dict, configuration: Config, folder: str) -> dict:
    """Every chart that can be drawn with the tables there are; a chart that fails is a warning, not a stop."""
    charts = {}
    drawings = [("01_pipeline_mensual", lambda: draw_pipeline_by_month(tables["pipeline_mes"], tables["pipeline_anio"], os.path.join(folder, "01_pipeline_mensual.png"), configuration)),
                ("02_ritmo_pipeline", lambda: draw_rhythm(tables["pipeline_mes"], os.path.join(folder, "02_ritmo_pipeline.png"), "vence_usd",
                                                          "02 · El ritmo de la pipeline: el USD que vence en el mismo mes de cada año", "USD que vence"))]
    if len(tables.get("plazo_mes", [])):
        drawings.append(("03_plazo", lambda: draw_terms(tables["plazo_mes"], os.path.join(folder, "03_plazo.png"))))
    if len(tables.get("mes_contra_mes", [])):
        compared = [dimension for dimension in charted_dimensions(tables["mes_contra_mes"], configuration) if dimension != TOTAL]
        drawings.append(("02b_mes_contra_mes", lambda: draw_month_against_month(tables["mes_contra_mes"], compared, os.path.join(folder, "02b_mes_contra_mes.png"),
                                                                                configuration.analysis_top_values)))
    if len(tables.get("tasa_mes_por", [])):
        drawings.append(("04_tasa", lambda: draw_rate(tables["tasa_mes_por"], fits, os.path.join(folder, "04_tasa.png"), configuration)))
    if len(tables.get("uplift_mes", [])):
        drawings.append(("05_uplift", lambda: draw_uplift(tables["uplift_mes"], tables.get("subidas_precio"), fits, os.path.join(folder, "05_uplift.png"))))
    if len(tables.get("adquisicion_mes", [])):
        drawings.append(("06_adquisicion", lambda: draw_acquisition(tables["adquisicion_mes"], fits, os.path.join(folder, "06_adquisicion.png"))))
    if len(tables.get("composicion_anual", [])):
        drawn_dimensions = charted_dimensions(tables["composicion_anual"], configuration)
        drawings.append(("07_composicion", lambda: draw_composition(tables["composicion_anual"], tables["composicion_cambio"], drawn_dimensions,
                                                                      os.path.join(folder, "07_composicion.png"), configuration.analysis_top_values)))
    if len(tables.get("estados_mes", [])):
        drawings.append(("08_estados", lambda: draw_states(tables["estados_mes"], tables.get("estados_tempranos", pd.DataFrame()),
                                                            tables.get("estados_horizonte", pd.DataFrame()), fits, os.path.join(folder, "08_estados.png"))))
    if len(tables.get("retail_to_subscription", [])):
        drawings.append(("09_retail_to_subscription", lambda: draw_retail_to_subscription(tables["retail_to_subscription"], fits, os.path.join(folder, "09_retail_to_subscription.png"))))
    for name, draw in drawings:
        try:
            with matplotlib.rc_context({"text.parse_math": False}):
                charts[name] = draw()
        except Exception as error:            # a chart that fails does not stop the analysis: it says why
            configuration.logger.warning(f"[{STAGE_1_LABEL}] the chart {name} could not be drawn: {type(error).__name__}: {error}")
    return charts


def charted_dimensions(composition: pd.DataFrame, configuration: Config) -> list:
    """The dimensions of the composition chart: the coarsest region, the first product level, the term and the origin."""
    present = list(composition["dimension"].unique())
    wanted = [region_columns_of(configuration)[0]]
    wanted += [dimension for dimension in configuration.business_mandatory_dims if "product" in dimension.lower()][:1]
    wanted += [name for name, _ in term_dimension(configuration)] + ["origen"]
    return [dimension for dimension in wanted if dimension in present]


# ═══════════════════════════════════════════════════════════════════════════════════
# THE STORY: ANALISIS_pipeline.md
# ═══════════════════════════════════════════════════════════════════════════════════

def percent(value, decimals: int = 1, signed: bool = False) -> str:
    if value is None or not np.isfinite(value):
        return "—"
    return f"{value:{'+' if signed else ''}.{decimals}%}"


def points(value, decimals: int = 2) -> str:
    if value is None or not np.isfinite(value):
        return "—"
    return f"{value:+.{decimals}f} pp"


def number(value, decimals: int = 0) -> str:
    if value is None or not np.isfinite(value):
        return "—"
    return f"{value:,.{decimals}f}"


def markdown_table(frame: pd.DataFrame, formats: dict) -> str:
    """A markdown table of the columns in formats (column → function of the value, or a header text when the value is
    already text)."""
    headers = [str(column) for column in formats]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for _, row in frame.iterrows():
        cells = []
        for column, formatter in formats.items():
            value = row[column] if column in row.index else np.nan
            cells.append(formatter(value) if callable(formatter) else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def trend_sentence(trends: pd.DataFrame, kpi: str, unit: str = "") -> str:
    """One sentence on a KPI's trend, from the trends table."""
    rows = trends[trends["kpi"] == kpi]
    if rows.empty:
        return ""
    row = rows.iloc[0]
    if row["tendencia"] == TOO_SHORT:
        return f"pocos meses para medir una tendencia ({int(row['meses'])})."
    in_points = bool(row["en_puntos"])
    slope = points(row["pendiente_anual"]) if in_points else percent(row["pendiente_relativa_anual"], 2, signed=True)
    verdict = {RISING: "sube", FALLING: "baja", STABLE: "es estable"}[row["tendencia"]]
    change = (points(row["variacion_12m"] * PERCENTAGE_POINTS) if in_points else percent(row["variacion_12m"], 1, signed=True))
    season = ""
    if row["estacional"] == 1:
        amplitude = points(row["amplitud_estacional"], 1) if in_points else percent(row["amplitud_estacional"], 1)
        season = (f" Tiene estacionalidad (amplitud {amplitude.lstrip('+')}"
                  + (f"; meses altos {month_list(row['meses_alto'])}" if row["meses_alto"] else "")
                  + (f"; bajos {month_list(row['meses_bajo'])}" if row["meses_bajo"] else "") + ").")
    elif row["meses"] >= 24 and np.isfinite(row["p_valor_mes"]):
        season = " Sin estacionalidad clara."
    return (f"{verdict} (pendiente {slope} al año, p = {row['p_valor_tendencia']:.2f}); los últimos 12 meses frente a los 12 "
            f"anteriores: {change}.{season}")


def month_list(text: str) -> str:
    return ", ".join(MONTH_NAMES[int(month) - 1] for month in str(text).split(",") if month)


def tell_the_analysis(tables: dict, charts: dict, configuration: Config, path: str, detector: str) -> list:
    """ANALISIS_pipeline.md: the one-page summary first, then one section per table with its chart. Returns the
    summary lines (what the stage shows on screen)."""
    current = configuration.calendar_boundaries()["current"]
    yearly, monthly, trends = tables["pipeline_anio"], tables["pipeline_mes"], tables["tendencias"]
    this_year = yearly[yearly["anio"] == current.year].iloc[0] if (yearly["anio"] == current.year).any() else None
    next_year = yearly[yearly["anio"] == current.year + 1].iloc[0] if (yearly["anio"] == current.year + 1).any() else None
    last_year = yearly[yearly["anio"] == current.year - 1].iloc[0] if (yearly["anio"] == current.year - 1).any() else None
    folder = os.path.dirname(path)

    def chart(name: str) -> str:
        return f"![{name}]({os.path.relpath(charts[name], folder)})" if name in charts else ""

    summary = []
    if this_year is not None:
        summary.append(f"**{current.year}** (año en curso): vence {money_label(this_year['vence_usd'])} "
                       f"({money_label(this_year['vence_usd_cerrado'])} ya cerrado, {money_label(this_year['vence_usd_futuro'])} por vencer); "
                       f"crece {percent(this_year['crecimiento_usd_vs_ano_anterior'], signed=True)} frente a {current.year - 1} en los mismos meses "
                       f"({int(this_year['meses_comparables'])} comparables).")
    if next_year is not None:
        summary.append(f"**{current.year + 1}**: ya se conocen {money_label(next_year['vence_usd'])} "
                       f"({int(next_year['meses_comparables'])} meses completos: {percent(next_year['crecimiento_usd_vs_ano_anterior'], signed=True)} "
                       f"frente a los mismos meses de {current.year}). Los meses que siguen aún se llenan.")
    if last_year is not None:
        summary.append(f"**{current.year - 1}**: vencieron {money_label(last_year['vence_usd'])}, renovaron {money_label(last_year['renovado_usd'])} "
                       f"(tasa {percent(last_year['tasa_unidades'])} en unidades, {percent(last_year['tasa_usd'])} en USD"
                       + (f", uplift {last_year['uplift']:.3f}" if np.isfinite(last_year["uplift"]) else "") + ").")
    summary.append(f"**Tasa de renovación** (unidades): {trend_sentence(trends, 'tasa_unidades')}")
    if (trends["kpi"] == "uplift").any():
        summary.append(f"**Revalorización**: {trend_sentence(trends, 'uplift')}")
    increases = tables.get("subidas_precio")
    if increases is not None and len(increases):
        active = int(increases["activa_hoy"].sum())
        summary.append(f"**Subidas de precio**: {len(increases)} detectadas en la historia ({detector}), {active} con su ciclo aún abierto hoy; "
                       f"la de más dinero: {increases.iloc[0]['price_group']} desde {increases.iloc[0]['inicio']} (+{percent(increases.iloc[0]['escalon'])}, "
                       f"{money_label(increases.iloc[0]['usd_renovado_ciclo'])} renovados en su ciclo).")
    if (trends["kpi"] == "adquisicion_unidades").any():
        summary.append(f"**Adquisición** (unidades por mes de venta): {trend_sentence(trends, 'adquisicion_unidades')}")
    if (trends["kpi"] == "parte_1_anio").any():
        summary.append(f"**Licencias de 1 año** (parte del USD que vence): {trend_sentence(trends, 'parte_1_anio')}")
    change = tables.get("composicion_cambio")
    if change is not None and len(change):
        latest = change[change["anio"] == change["anio"].max()].sort_values("cambio_composicion", ascending=False)
        summary.append(f"**Composición** ({latest.iloc[0]['meses']} frente a {latest.iloc[0]['meses_ano_anterior']}): la que más se mueve es "
                       f"{latest.iloc[0]['dimension']} ({percent(latest.iloc[0]['cambio_composicion'])} del USD cambia de valor; "
                       f"sube {latest.iloc[0]['mayor_subida']}, baja {latest.iloc[0]['mayor_bajada']}).")
    for kpi in [row for row in trends["kpi"] if row.endswith("_primer_mes")]:
        state = kpi[:-len("_primer_mes")]
        summary.append(f"**{state} temprano** (ya en el estado en su primer mes de vida, licencias de 1 año): {trend_sentence(trends, kpi)}")
    for kpi in [row for row in trends["kpi"] if row.endswith("_parte")]:
        summary.append(f"**{kpi[:-len('_parte')]}** (parte final de lo que vence): {trend_sentence(trends, kpi)}")
    if (trends["kpi"] == "retail_to_subscription_usd").any():
        summary.append(f"**Retail to subscription**: {trend_sentence(trends, 'retail_to_subscription_usd')}")

    lines = [f"# Análisis de la pipeline · mes en curso {current}", "",
             "La materia prima del forecast, descrita antes de hacer números con ella: la pipeline pasada con su resultado y la "
             "futura tal cual viene. Todo lo de aquí es descriptivo y sale solo de la pipeline. Las tablas están en SQL como "
             f"`{configuration.table_prefix}e1_*`.", "",
             "**Cerrado**: un mes anterior al mes en curso, con su resultado. **Futuro**: el mes en curso y los que siguen. "
             "**Completo**: un mes futuro cuyas licencias de 1 año ya se vendieron o renovaron (hasta "
             f"{current + MONTHS_PER_YEAR - 1}); los meses posteriores aún se llenan y no se comparan con el año anterior.", "",
             "## En una página", ""]
    lines += [f"- {line}" for line in summary]
    section = iter(range(1, 20))
    lines += ["", f"## {next(section)} · La pipeline: cuánto vence y si crece", "", chart("01_pipeline_mensual"), "", chart("02_ritmo_pipeline"), "",
              "Por año (el crecimiento, sobre los meses comparables: cerrados o completos, frente a los mismos meses del año anterior):", "",
              markdown_table(yearly, {"anio": lambda value: str(int(value)), "estado": str, "meses": lambda value: str(int(value)),
                                      "meses_cerrados": lambda value: str(int(value)), "vence_usd": money_label,
                                      "vence_usd_cerrado": money_label, "vence_usd_futuro": money_label, "renovado_usd": money_label,
                                      "tasa_unidades": percent, "tasa_usd": percent, "uplift": lambda value: number(value, 3),
                                      "meses_comparables": lambda value: str(int(value)),
                                      "crecimiento_usd_vs_ano_anterior": lambda value: percent(value, signed=True),
                                      "crecimiento_unidades_vs_ano_anterior": lambda value: percent(value, signed=True)}),
              "", f"- USD que vence al mes: {trend_sentence(trends, 'vence_usd')}", f"- Unidades que vencen al mes: {trend_sentence(trends, 'vencen_unidades')}", ""]
    comparison = tables.get("mes_contra_mes")
    if comparison is not None and len(comparison):
        last = comparison[comparison["comparacion"] == LAST_MONTH]
        total = last[last["dimension"] == TOTAL].iloc[0]
        lines += [f"## {next(section)} · {total['mes_hoy']} frente a {total['mes_antes']}: dónde están las diferencias", "",
                  f"Lo renovado pasó de {money_label(total['renovado_usd_antes'])} a {money_label(total['renovado_usd_hoy'])} "
                  f"({money_label(total['renovado_usd_diferencia'])}): venció {money_label(total['vence_usd_antes'])} → "
                  f"{money_label(total['vence_usd_hoy'])} (efecto pipeline {money_label(total['efecto_pipeline_usd'])}), la tasa en unidades "
                  f"{percent(total['tasa_unidades_antes'])} → {percent(total['tasa_unidades_hoy'])} (efecto tasa {money_label(total['efecto_tasa_usd'])})"
                  + (f", el uplift {total['uplift_antes']:.3f} → {total['uplift_hoy']:.3f} (efecto uplift {money_label(total['efecto_uplift_usd'])})"
                     if np.isfinite(total["uplift_hoy"]) else "") + ".", "", chart("02b_mes_contra_mes"), "",
                  "Los dos valores que más mueven lo renovado en cada dimensión (los estados del cliente, en la tabla):", ""]
        states = set(configuration.structural_timevarying_dims)
        movers = last[(last["dimension"] != TOTAL) & ~last["dimension"].isin(states)].copy()
        movers["_peso"] = movers["renovado_usd_diferencia"].abs()
        movers = movers.sort_values("_peso", ascending=False).groupby("dimension", sort=False).head(2)
        order = {name: position for position, name in enumerate(last["dimension"].unique())}     # as the table lists them
        movers["_orden"] = movers["dimension"].map(order)
        movers = movers.sort_values(["_orden", "_peso"], ascending=[True, False])
        lines += [markdown_table(movers, {"dimension": str, "valor": str, "vence_usd_antes": money_label, "vence_usd_hoy": money_label,
                                          "renovado_usd_antes": money_label, "renovado_usd_hoy": money_label,
                                          "renovado_usd_diferencia": money_label, "tasa_unidades_antes": percent, "tasa_unidades_hoy": percent,
                                          "efecto_pipeline_usd": money_label, "efecto_tasa_usd": money_label, "efecto_uplift_usd": money_label}), ""]
        twelve = comparison[(comparison["comparacion"] == LAST_12_MONTHS) & (comparison["dimension"] == TOTAL)]
        if len(twelve):
            total_12 = twelve.iloc[0]
            lines += [f"Los últimos 12 meses cerrados ({total_12['mes_hoy']}) frente a los 12 anteriores ({total_12['mes_antes']}): renovado "
                      f"{money_label(total_12['renovado_usd_antes'])} → {money_label(total_12['renovado_usd_hoy'])}; efecto pipeline "
                      f"{money_label(total_12['efecto_pipeline_usd'])}, efecto tasa {money_label(total_12['efecto_tasa_usd'])}, efecto uplift "
                      f"{money_label(total_12['efecto_uplift_usd'])}. El detalle por dimensión está en `{configuration.table_prefix}{TABLE_MONTH_AGAINST_MONTH}` "
                      f"(`comparacion = '{LAST_12_MONTHS}'`).", ""]
    if len(tables.get("plazo_mes", [])):
        by_year = tables["plazo_mes"][tables["plazo_mes"]["completa"] == 1].groupby(["anio", "plazo_anios"])[["vence_usd", "vencen_unidades"]].sum().reset_index()
        totals = by_year.groupby("anio")["vence_usd"].transform("sum")
        by_year["parte_usd"] = by_year["vence_usd"] / totals.where(totals > 0)
        lines += [f"## {next(section)} · El plazo de las licencias", "", chart("03_plazo"), "",
                  markdown_table(by_year, {"anio": lambda value: str(int(value)), "plazo_anios": lambda value: str(int(value)),
                                           "vence_usd": money_label, "vencen_unidades": number, "parte_usd": percent}),
                  "", f"- Parte de 1 año: {trend_sentence(trends, 'parte_1_anio')}", ""]
    if len(tables.get("tasa_mes_por", [])):
        by_year = tables["tasa_mes_por"].groupby(["dimension", "valor", "anio"])[["vencen_unidades", "renovadas_unidades"]].sum().reset_index()
        by_year["tasa_unidades"] = by_year["renovadas_unidades"] / by_year["vencen_unidades"].where(by_year["vencen_unidades"] > 0)
        wide = by_year.pivot_table(index=["dimension", "valor"], columns="anio", values="tasa_unidades").reset_index()
        biggest = by_year.groupby(["dimension", "valor"])["vencen_unidades"].sum().sort_values(ascending=False)
        wide = wide.set_index(["dimension", "valor"]).loc[[key for key in biggest.index if key in wide.set_index(["dimension", "valor"]).index][:configuration.analysis_top_values * 3]].reset_index()
        formats = {"dimension": str, "valor": str, **{year: (lambda value: percent(value)) for year in [column for column in wide.columns if isinstance(column, (int, np.integer))]}}
        lines += [f"## {next(section)} · La tasa de renovación real", "", chart("04_tasa"), "",
                  "Por año y dimensión (unidades; las combinaciones con más unidades):", "", markdown_table(wide, formats), "",
                  f"- En unidades: {trend_sentence(trends, 'tasa_unidades')}", f"- En USD: {trend_sentence(trends, 'tasa_usd')}", ""]
    if len(tables.get("uplift_mes", [])):
        lines += [f"## {next(section)} · La revalorización y las subidas de precio", "", chart("05_uplift"), "",
                  f"- Revalorización: {trend_sentence(trends, 'uplift')}"]
        if (trends["kpi"] == "uplift_aislado").any():
            lines.append(f"- Renovaciones aisladas (sin descuentos de retención): {trend_sentence(trends, 'uplift_aislado')}")
        if increases is not None and len(increases):
            lines += ["", f"Subidas detectadas (el detector del paso 3.1 sobre `{detector}`; una subida es un escalón de al menos "
                          f"{percent(configuration.price_step_threshold, 0)} sobre la media de los 12 meses anteriores que dura "
                          f"{configuration.price_persistence_months} meses):", "",
                      markdown_table(increases.head(configuration.analysis_top_values * 2),
                                     {"price_group": str, "inicio": str, "fin_ciclo": str, "escalon": lambda value: percent(value, signed=True),
                                      "uplift_antes": lambda value: number(value, 3), "uplift_ciclo": lambda value: number(value, 3),
                                      "meses_vistos": lambda value: str(int(value)), "usd_renovado_ciclo": money_label,
                                      "activa_hoy": lambda value: "sí" if value == 1 else "no"})]
        elif increases is not None:
            lines.append("- Ninguna subida de precio detectada en la historia.")
        pending = tables.get("subidas_pendientes")
        if pending is not None and len(pending):
            lines += ["", f"Escalones al final de la historia aún sin confirmar: {len(pending)} grupos (se confirman cuando cierren sus meses)."]
        lines.append("")
    if len(tables.get("adquisicion_mes", [])):
        acquisition = tables["adquisicion_mes"]
        observable = acquisition[acquisition["observable"] == 1]
        by_year = observable.groupby(["anio_venta", "plazo_anios"]).agg(meses=("mes_venta", "nunique"), vendidas_unidades=("vendidas_unidades", "sum"),
                                                                        vendido_usd=("vendido_usd", "sum")).reset_index()
        lines += [f"## {next(section)} · La adquisición", "", chart("06_adquisicion"), "",
                  "Por año de venta y plazo, en los meses de venta observables (sus licencias vencen dentro del extracto): unidades y el USD "
                  "con que vencerán.", "",
                  markdown_table(by_year, {"anio_venta": lambda value: str(int(value)), "plazo_anios": lambda value: str(int(value)),
                                           "meses": lambda value: str(int(value)), "vendidas_unidades": number, "vendido_usd": money_label}),
                  "", f"- Unidades (1 año): {trend_sentence(trends, 'adquisicion_unidades')}", f"- USD (1 año): {trend_sentence(trends, 'adquisicion_usd')}", ""]
    if len(tables.get("composicion_anual", [])):
        change_table = tables["composicion_cambio"]
        recent = change_table[change_table["anio"] >= change_table["anio"].max() - 1].sort_values(["anio", "cambio_composicion"], ascending=[False, False])
        lines += [f"## {next(section)} · La composición de la pipeline", "", chart("07_composicion"), "",
                  "Cuánto cambia la composición frente al año anterior, sobre los mismos meses (Σ |Δ parte| / 2 del USD que vence; 0 = la misma). "
                  f"Los dos últimos años; el resto en `{configuration.table_prefix}{TABLE_COMPOSITION_CHANGE}`:", "",
                  markdown_table(recent, {"anio": lambda value: str(int(value)), "meses": str, "meses_ano_anterior": str, "dimension": str,
                                          "valores": lambda value: str(int(value)), "cambio_composicion": percent, "mayor_subida": str, "mayor_bajada": str}), ""]
    if len(tables.get("estados_mes", [])):
        lines += [f"## {next(section)} · Los estados del cliente", "", chart("08_estados"), ""]
        for kpi in [row for row in trends["kpi"] if row.endswith("_parte")]:
            lines.append(f"- {kpi[:-len('_parte')]} (parte final, meses cerrados): {trend_sentence(trends, kpi)}")
        for kpi in [row for row in trends["kpi"] if row.endswith("_primer_mes")]:
            lines.append(f"- {kpi[:-len('_primer_mes')]} ya en su primer mes de vida (licencias de 1 año): {trend_sentence(trends, kpi)}")
        horizon = tables.get("estados_horizonte")
        if horizon is not None and len(horizon):
            lines += ["", "Los meses que vienen, al mismo horizonte que la cohorte de hace un año:", "",
                      markdown_table(horizon, {"mes": str, "estado": str, "horizonte_meses": lambda value: str(int(value)), "vencen_unidades": number,
                                               "parte_visible_hoy": percent, "parte_visible_ano_anterior_mismo_horizonte": percent, "parte_final_ano_anterior": percent})]
        lines.append("")
    if len(tables.get("retail_to_subscription", [])):
        lines += [f"## {next(section)} · El retail to subscription", "", chart("09_retail_to_subscription"), "",
                  f"- Ingresos: {trend_sentence(trends, 'retail_to_subscription_usd')}", ""]
    if len(tables.get("transiciones_plazo", [])):
        transitions = tables["transiciones_plazo"]
        formats = {"anio": lambda value: str(int(value)), "plazo_origen_anios": lambda value: str(int(value)), "renovadas_unidades": number}
        formats.update({column: percent for column in transitions.columns if column.startswith("parte_a_")})
        formats["parte_destino_conocido"] = percent
        lines += [f"## {next(section)} · A qué plazo renuevan", "", markdown_table(transitions, formats), ""]
    lines += [f"## {next(section)} · Las tendencias, en una tabla", "",
              "Pendiente anual: en puntos para las partes y las tasas, relativa a la media para el resto. p < "
              f"{configuration.dynamics_significance:g} = tendencia; la estacionalidad, con al menos {configuration.analysis_season_min_months} meses.", "",
              markdown_table(trends, {"kpi": str, "meses": lambda value: str(int(value)), "media_ultimos_12": lambda value: number(value, 3),
                                      "media_12_anteriores": lambda value: number(value, 3),
                                      "pendiente_anual": lambda value: number(value, 3), "pendiente_relativa_anual": lambda value: percent(value, signed=True),
                                      "p_valor_tendencia": lambda value: number(value, 2), "tendencia": str, "estacional": lambda value: "sí" if value == 1 else "no",
                                      "amplitud_estacional": lambda value: number(value, 3), "meses_alto": month_list, "meses_bajo": month_list}), ""]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return summary


# ═══════════════════════════════════════════════════════════════════════════════════
# THE STAGE
# ═══════════════════════════════════════════════════════════════════════════════════

def analyse_the_pipeline(raw: pd.DataFrame, configuration: Config) -> dict:
    """Stage 1: every table of the analysis, written as sff_e1_*; the charts and ANALISIS_pipeline.md in
    <output_folder>/analisis. Returns {"tables", "charts", "markdown", "summary", "seconds"}."""
    started = time.time()
    configuration.log_block_start(STAGE_1_LABEL, 1, STAGE_1_NAME, STAGE_1_PURPOSE)
    configuration.log_step_start(STAGE_1_LABEL, STAGE_1_NAME, STAGE_1_PURPOSE, STAGE_1_ACTIONS, STAGE_1_OUTPUT)
    tables = {}

    # [1] the rows
    rows, time_series_rows = pipeline_rows_of(raw, configuration)
    current = configuration.calendar_boundaries()["current"]
    configuration.log_action(STAGE_1_LABEL, 1, f"{len(rows):,} rows of the pipeline ({int(rows[IS_CLOSED].sum()):,} of closed months, "
                                               f"{int((~rows[IS_CLOSED]).sum()):,} of the current month and after; complete up to "
                                               f"{current + MONTHS_PER_YEAR - 1}) · {len(time_series_rows):,} rows of retail to subscription")

    # [2] the pipeline by month and by year
    tables["pipeline_mes"] = pipeline_by_month(rows, configuration)
    tables["pipeline_anio"] = pipeline_by_year(tables["pipeline_mes"], configuration)
    yearly = tables["pipeline_anio"]
    configuration.log_action(STAGE_1_LABEL, 2, " · ".join(f"{int(row['anio'])}: {money_label(row['vence_usd'])} due"
                                                          + (f" ({row['crecimiento_usd_vs_ano_anterior']:+.1%} vs the year before, comparable months)"
                                                             if np.isfinite(row["crecimiento_usd_vs_ano_anterior"]) else "") for _, row in yearly.iterrows()))

    # [3] the terms
    tables["plazo_mes"] = term_by_month(rows, configuration)
    configuration.log_action(STAGE_1_LABEL, 3, f"{tables['plazo_mes']['plazo_anios'].nunique()} terms" if len(tables["plazo_mes"]) else "no term column: every licence counted as 1 year")

    # [4] the rate
    tables["tasa_mes_por"] = rate_by_month(rows, configuration)
    configuration.log_action(STAGE_1_LABEL, 4, f"the rate by month for {tables['tasa_mes_por']['dimension'].nunique()} dimensions")

    # [5] the last closed month against the same month a year before
    tables["mes_contra_mes"] = month_against_month(rows, configuration)
    if len(tables["mes_contra_mes"]):
        total = tables["mes_contra_mes"][(tables["mes_contra_mes"]["comparacion"] == LAST_MONTH) & (tables["mes_contra_mes"]["dimension"] == TOTAL)].iloc[0]
        configuration.log_action(STAGE_1_LABEL, 5, f"{total['mes_hoy']} against {total['mes_antes']}: renewed {money_label(total['renovado_usd_antes'])} → "
                                                   f"{money_label(total['renovado_usd_hoy'])} (pipeline {money_label(total['efecto_pipeline_usd'])}, rate "
                                                   f"{money_label(total['efecto_tasa_usd'])}, uplift {money_label(total['efecto_uplift_usd'])})")
    else:
        configuration.log_action(STAGE_1_LABEL, 5, "no closed month to compare")

    # [6] the uplift and the increases
    uplift = uplift_and_increases(rows, configuration)
    tables["uplift_mes"], tables["subidas_precio"], tables["subidas_pendientes"] = uplift["monthly"], uplift["increases"], uplift["pending"]
    configuration.log_action(STAGE_1_LABEL, 6, f"{len(uplift['increases'])} price increases detected on {uplift['detector'] or '—'}"
                                               f"{', ' + str(len(uplift['pending'])) + ' steps not confirmed yet' if len(uplift['pending']) else ''}")

    # [7] the acquisition
    tables["adquisicion_mes"] = acquisition_by_month(rows, configuration)
    configuration.log_action(STAGE_1_LABEL, 7, f"the acquisition by month of sale: {tables['adquisicion_mes']['mes_venta'].nunique()} months"
                             if len(tables["adquisicion_mes"]) else "no acquisition column: no acquisition read")

    # [8] the composition
    if len(composition_dimensions(rows, configuration)):
        tables["composicion_anual"], tables["composicion_cambio"] = composition_by_year(rows, configuration)
    else:
        tables["composicion_anual"], tables["composicion_cambio"] = pd.DataFrame(), pd.DataFrame()
    configuration.log_action(STAGE_1_LABEL, 8, f"the composition by {tables['composicion_anual']['dimension'].nunique()} dimensions"
                             if len(tables["composicion_anual"]) else "no dimension to read the composition by")

    # [9] the states
    tables["estados_mes"] = states_by_month(rows, configuration)
    tables["estados_tempranos"] = early_states(rows, configuration)
    tables["estados_horizonte"] = states_at_horizon(rows, configuration)
    configuration.log_action(STAGE_1_LABEL, 9, f"{tables['estados_mes']['estado'].nunique() if len(tables['estados_mes']) else 0} states; "
                                               f"{tables['estados_tempranos']['estado'].nunique() if len(tables['estados_tempranos']) else 0} dated "
                                               f"(early share and the same horizon a year ago)")

    # [10] the other universe and the term transitions
    tables["retail_to_subscription"] = retail_to_subscription_by_month(time_series_rows, configuration)
    tables["transiciones_plazo"] = term_transitions_by_year(rows, configuration)
    configuration.log_action(STAGE_1_LABEL, 10, f"retail to subscription: {len(tables['retail_to_subscription'])} closed months · term transitions: "
                                               f"{'yes' if len(tables['transiciones_plazo']) else 'not in the extract'}")
    del rows, time_series_rows

    # [11] the trends
    tables["tendencias"], fits = trends_table(kpi_series(tables, configuration), configuration)
    verdicts = tables["tendencias"]["tendencia"].value_counts().to_dict()
    configuration.log_action(STAGE_1_LABEL, 11, f"{len(tables['tendencias'])} KPIs: " + ", ".join(f"{count} {verdict}" for verdict, count in verdicts.items()))

    # [12] write, draw, tell
    folder = os.path.join(configuration.output_folder, ANALYSIS_FOLDER)
    os.makedirs(folder, exist_ok=True)
    written = []
    for name, table_name in TABLES_WRITTEN.items():
        table = tables.get(name)
        if table is not None and len(table):
            write_plain_table(table, table_name, configuration)
            written.append(f"{configuration.table_prefix}{table_name}")
    charts = draw_the_charts(tables, fits, configuration, folder)
    markdown_path = os.path.join(folder, MARKDOWN_NAME)
    summary = tell_the_analysis(tables, charts, configuration, markdown_path, uplift["detector"])
    configuration.log_action(STAGE_1_LABEL, 12, f"{len(written)} tables written ({', '.join(written)}) · {len(charts)} charts · {markdown_path} "
                                                f"· {time.time() - started:.1f}s")
    configuration.logger.doc(f"[{STAGE_1_LABEL}] VALORACIÓN · la pipeline en una página:")
    for line in summary:
        configuration.logger.doc(f"[{STAGE_1_LABEL}]    {line.replace('**', '')}")
    configuration.show_table(tables["tendencias"].drop(columns=["que_es", "en_puntos", "primer_mes", "media"]))
    return {"tables": tables, "charts": charts, "markdown": markdown_path, "summary": summary, "seconds": time.time() - started}


TABLES_WRITTEN = {"pipeline_mes": TABLE_PIPELINE_BY_MONTH, "pipeline_anio": TABLE_PIPELINE_BY_YEAR, "plazo_mes": TABLE_TERM_BY_MONTH,
                  "tasa_mes_por": TABLE_RATE_BY_MONTH, "mes_contra_mes": TABLE_MONTH_AGAINST_MONTH, "uplift_mes": TABLE_UPLIFT_BY_MONTH, "subidas_precio": TABLE_PRICE_INCREASES,
                  "adquisicion_mes": TABLE_ACQUISITION_BY_MONTH, "composicion_anual": TABLE_COMPOSITION_BY_YEAR,
                  "composicion_cambio": TABLE_COMPOSITION_CHANGE, "estados_mes": TABLE_STATES_BY_MONTH, "estados_tempranos": TABLE_EARLY_STATES,
                  "estados_horizonte": TABLE_STATES_AT_HORIZON, "retail_to_subscription": TABLE_RETAIL_TO_SUBSCRIPTION,
                  "transiciones_plazo": TABLE_TERM_TRANSITIONS, "tendencias": TABLE_TRENDS}
