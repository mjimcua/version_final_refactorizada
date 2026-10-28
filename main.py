"""
main.py — Runs SFF on the production extract, or on the synthetic raw, stage by stage (stages.py, PLAN_etapas.md).

    python main.py              # the production extract (SQL Server)
    python main.py sintetico    # the synthetic raw of the tests
    python main.py parecido     # the synthetic that looks like production (synthetic_real.py), current month 2026-09
    python main.py parecido 2026-10    # the same, with another current month

THE STAGES TO RUN: the switches RUN_STAGE_0_DATA, RUN_STAGE_1_ANALYSIS, RUN_STAGE_2_LEARNING, RUN_FORECAST and RUN_REPORT
below, or on the command line:
    python main.py sin_datos      # the forecast on the dataset written by the last stage 0 (no SQL)
    python main.py sin_analisis   # without the analysis of the pipeline (stage 1)
    python main.py sin_aprender   # the forecast with the dynamics persisted in this cut (step 4.1 not examined again)
    python main.py escenario      # sin_datos + sin_analisis + sin_aprender: a scenario of the month (registered as an escenario)
    python main.py referencia     # the run delivered to the business: registered and frozen as the reference
    python main.py solo_datos     # stage 0 only: read the pipeline, test it and write it
    python main.py solo_analisis  # stage 1 only, on the dataset written: the tables sff_e1_* and ANALISIS_pipeline.md
    python main.py informe        # also the report (informe_forecast.py) after the forecast

The Config is declared here and only here: its columns, its calendar and where the raw
comes from. Each step adds one line to run().

WHAT IS PRIVATE TO THIS MACHINE lives in entorno_local.py, next to this file and never in the zip of the project:
the SQL server, the database, the driver, the schema, the query of the raw (and optionally the login, the table prefix
and the current month). A new main.py does not touch it. The first time: copy entorno_local_ejemplo.py to
entorno_local.py and fill it in. Only production reads it: the synthetics run without it.
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import os
import sys

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from pipeline import Orchestrator
from config import Config
from stages import StagesToRun, run_stages


# ─── named constants ─────────────────────────────────────────────────────────────
LOCAL_ENVIRONMENT_MODULE = "entorno_local"        # the private settings of this machine (entorno_local.py)
LOCAL_ENVIRONMENT_REQUIRED = ["SQL_SERVER", "SQL_DATABASE", "SQL_DRIVER", "SQL_SCHEMA", "RAW_EXTRACT_QUERY"]
PRODUCTION_OUTPUT_FOLDER = "salida"
PRODUCTION_LOG_FILE = os.path.join(PRODUCTION_OUTPUT_FOLDER, "sff_ejecucion.log")
PRODUCTION_CURRENT_MONTH = "01/10/2026"          # entorno_local.CURRENT_MONTH, when it is there, replaces it
# the acquisition team's forecast of 2026 per subregion, in thousands of USD (27-oct-2026): the simulated acquisitions
# complete the year of every subregion up to it (step 5.1). Its LATAM line (5,861) included Canada; the file has the
# subregions only, which add up to the 25,000 of the total
ACQUISITION_TARGETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "objetivos_adquisicion_2026.csv")
# the term transitions of a renewal (28-oct-2026): True once the extract brings the six columns
# total_renewed_units_to_1y … total_renewed_usd_to_3y (of the renewed units and USD of a row, those that renewed to a
# licence of 1, 2 or 3 years). Step 7.2 then projects the renewals of the window by the share of every destination
TERM_TRANSITION_COLUMNS_IN_EXTRACT = True
TERM_TRANSITION_COLUMNS = dict(renewed_units_to_1y_col="total_renewed_units_to_1y",
                               renewed_units_to_2y_col="total_renewed_units_to_2y",
                               renewed_units_to_3y_col="total_renewed_units_to_3y",
                               renewed_usd_to_1y_col="total_renewed_usd_to_1y",
                               renewed_usd_to_2y_col="total_renewed_usd_to_2y",
                               renewed_usd_to_3y_col="total_renewed_usd_to_3y")
# where the share of every destination is learned, finest first (the origin term is always added); a group takes the
# first level with term_transition_min_renewed_units renewals in the last 12 closed months; [] = the portfolio
TERM_TRANSITION_LEVELS = [["tr_regional_level_3", "tr_product_level_1"], ["tr_regional_level_1", "tr_product_level_1"],
                          ["tr_product_level_1"], []]
SYNTHETIC_KEYWORD = "sintetico"
SYNTHETIC_OUTPUT_FOLDER = "salida"
SYNTHETIC_DATABASE = os.path.join(SYNTHETIC_OUTPUT_FOLDER, "sff_sintetico.db")
LIKE_REAL_KEYWORD = "parecido"                     # python main.py parecido [2026-10]: the synthetic that looks like production
LIKE_REAL_DATABASE = os.path.join(SYNTHETIC_OUTPUT_FOLDER, "sff_parecido.db")
LIKE_REAL_LEVELS = os.path.join(SYNTHETIC_OUTPUT_FOLDER, "sff_levels_parecido.json")
LIKE_REAL_SEED = 11
# the LEVERS agreed with the business (levers.py): palancas.csv next to this file, when it is there (copy
# palancas_ejemplo.csv and set estado = acordada in the levers to apply). Without it: the forecast of the method
LEVERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "palancas.csv")
# ─── THE STAGES TO RUN (stages.py · PLAN_etapas.md) ───────────────────────────────
RUN_STAGE_0_DATA = True        # 0 · read the pipeline with its SQL, test it and write it (sff_e0_dataset).
                               #     False: the forecast reads the dataset of the last stage 0 of this cut (no SQL): the
                               #     scenarios of a month after the first run
RUN_STAGE_1_ANALYSIS = True    # 1 · describe the pipeline before predicting it (sff_e1_*, salida/analisis/ANALISIS_pipeline.md)
RUN_STAGE_2_LEARNING = True    # 2 · learn the forecast dynamics and persist them (sff_fd_*: today the maturation of the customer
                               #     states). False: read the ones persisted in this cut (the curve is not examined again)
RUN_FORECAST = True            # blocks 1 to 8: the forecast, its exam and its output (sff_*)
RUN_REPORT = False             # informe_forecast.py over the tables of the forecast (or of the last one in SQL)
REPORT_QUESTIONS = []          # [] = every question; or some, e.g. ["9.1"]
RUN_KIND = "baseline"          # the register of runs (runs.py: sff_ejecuciones): baseline · escenario · referencia (frozen)
RUN_NOTE = ""                  # what this run is, for the register (e.g. "campaña cancel DACH +3 pp")
SKIP_DATA_KEYWORD = "sin_datos"          # python main.py sin_datos: RUN_STAGE_0_DATA = False for this run
SKIP_ANALYSIS_KEYWORD = "sin_analisis"   # python main.py sin_analisis: RUN_STAGE_1_ANALYSIS = False for this run
SKIP_LEARNING_KEYWORD = "sin_aprender"   # python main.py sin_aprender: RUN_STAGE_2_LEARNING = False for this run
SCENARIO_KEYWORD = "escenario"           # python main.py escenario: sin_datos + sin_analisis + sin_aprender, registered as an escenario
REFERENCE_KEYWORD = "referencia"         # python main.py referencia: the run is frozen as the reference
ONLY_DATA_KEYWORD = "solo_datos"         # python main.py solo_datos: stage 0 only
ONLY_ANALYSIS_KEYWORD = "solo_analisis"  # python main.py solo_analisis: stage 1 only, on the dataset written
REPORT_KEYWORD = "informe"               # python main.py informe: RUN_REPORT = True for this run


# ═══════════════════════════════════════════════════════════════════════════════════
# THE TWO CONFIGS
# ═══════════════════════════════════════════════════════════════════════════════════

def local_environment():
    """The private settings of this machine: the module entorno_local.py next to main.py (copied from
    entorno_local_ejemplo.py and filled in once). It stops with what to do when it is missing or incomplete."""
    try:
        import entorno_local
    except ModuleNotFoundError as error:
        if error.name != LOCAL_ENVIRONMENT_MODULE:
            raise
        raise FileNotFoundError(f"falta {LOCAL_ENVIRONMENT_MODULE}.py junto a main.py ({os.path.dirname(os.path.abspath(__file__))}): "
                                f"copia entorno_local_ejemplo.py como {LOCAL_ENVIRONMENT_MODULE}.py y rellena el servidor, "
                                f"la base, el schema y la query del extracto") from None
    missing = [name for name in LOCAL_ENVIRONMENT_REQUIRED
               if not str(getattr(entorno_local, name, "") or "").strip() or "..." in str(getattr(entorno_local, name))]
    if missing:
        raise ValueError(f"{LOCAL_ENVIRONMENT_MODULE}.py ({entorno_local.__file__}) no tiene rellenos: {', '.join(missing)}")
    return entorno_local


def production_engine(environment=None):
    """The production SQL Server: the raw is read from it and the tables are written to it. Windows authentication
    unless entorno_local gives SQL_USER and SQL_PASSWORD. fast_executemany: pyodbc sends every chunk of to_sql in one
    round trip (without it, one INSERT per row: a table of a million rows takes minutes instead of seconds)."""
    environment = environment or local_environment()
    user, password = getattr(environment, "SQL_USER", None), getattr(environment, "SQL_PASSWORD", None)
    query = {"driver": environment.SQL_DRIVER}
    if not user:
        query["trusted_connection"] = "yes"
    connection_url = URL.create("mssql+pyodbc", username=user or None, password=password or None,
                                host=environment.SQL_SERVER, database=environment.SQL_DATABASE, query=query)
    return create_engine(connection_url, fast_executemany=True)


class ProductionConfig(Config):
    def read_raw(self) -> pd.DataFrame:
        return pd.read_sql(self.raw_extract_sql, self.sql_engine)


class SyntheticConfig(Config):
    def read_raw(self) -> pd.DataFrame:
        from synthetic_v3 import build_raw
        return build_raw(7, with_discount_pct=True)


class LikeRealConfig(Config):
    def read_raw(self) -> pd.DataFrame:
        from synthetic_real import build_raw_like_real
        return build_raw_like_real(seed=LIKE_REAL_SEED)


def production_configuration() -> Config:
    """The production extract (Kamelot), with the Config of the real run of 19-oct-2026: the same columns and
    choices as like_real_configuration, which reproduces it. Names marked [por confirmar] must be checked
    against the extract: step 1.1 names every column that is missing or has no role, and stops."""
    os.makedirs(PRODUCTION_OUTPUT_FOLDER, exist_ok=True)          # the log file, the report and the charts go there
    environment = local_environment()                             # entorno_local.py: what is private to this machine
    return ProductionConfig(
        # where the raw is read from and the tables are written to (entorno_local.py)
        sql_engine=production_engine(environment),
        sql_schema=environment.SQL_SCHEMA,
        table_prefix=getattr(environment, "TABLE_PREFIX", None) or "sff_",
        raw_extract_sql=environment.RAW_EXTRACT_QUERY,
        # the log: every line and every table to the file; the console (the notebook) only warnings, failures and
        # the final table. A full run with the real extract is ~2,000 lines and ~100 tables: rendered in the browser,
        # it ran out of memory (26-oct-2026). console_log_level=None shows everything again
        log_file=PRODUCTION_LOG_FILE,
        console_log_level="WARNING",
        # the calendar (entorno_local.CURRENT_MONTH, when it is there, so a new main.py does not move it)
        current_month=getattr(environment, "CURRENT_MONTH", None) or PRODUCTION_CURRENT_MONTH,
        test_months=6,                       # 6 exam months, as in the run of 19-oct: with 3, no gain can be significant
        # the dimensions
        business_mandatory_dims=["tr_regional_level_1", "tr_regional_level_2", "tr_regional_level_3",
                                 "tr_product_level_1", "tr_product_level_2", "tr_renewal_type",
                                 "tr_term", "tr_band", "tr_master_partner_code"],   # [por confirmar] tr_purchase_type was in the 29-sep extract, not in the 19-oct one
        # term and band keep their raw value; step 1.2 adds tr_term_level_1 / tr_band_level_1 (their values
        # grouped by the renewal rate). The groups are kept in salida/sff_levels.json
        leveled_dims={"tr_term": "ordinal", "tr_band": "ordinal"},
        structural_timevarying_dims={"dormant": "negative", "softcancel": "negative",
                                     "not_installed": "negative"},            # [por confirmar] the signs
        # the states whose extract says WHEN they were set (<state>_month_0 … <state>_month_12, the units in the state k months
        # before due): the extract carries softcancel's since 21-oct-2026 and dormant's since 28-oct-2026; step 1.1 fails
        # if they are missing. Every curve passes its exam in step 4.1 or the state takes its historical share
        maturation_dims=["softcancel", "dormant"],
        extra_renovacion=["net_new", "prev_OperationGroup"],
        # no extra_revalorizacion: the 19-oct extract carries no price_cap / msrp_increased (the increases are detected in 3.1)   [por confirmar]
        # the discount: ONE column, both sides (the bucket is derived with the default edges,
        # the same as the extract's old discount_interval)
        discount_value_column="discount",
        sku_column="sku",                     # the SKU: formula input for the price scenarios of step 3.2
        # the other columns of the extract
        extra_measure_cols=["total_reacquired_units", "total_reacquired_usd"],   # an AUV is USD / units: computed, not read
        # the exact base of the uplift: the USD that was falling due of the contracts that RENEWED (built per
        # licence and summed). With it, the uplift is pure revaluation, conditional on renewing
        renewed_pipeline_usd_col="total_tr_usd_renewed",
        # the ISOLATED renewals: here, the licences that renew the same product (sku base key), in the same BU, as a
        # Retention, and never had a softcancel; their base is total_tr_usd_renewed (fixed rate), and the ratio of
        # every licence is total_renewed_usd / total_tr_usd_renewed: the reference to see a price increase
        # without the retention discounts
        # no isolated_pipeline_units_col: an isolated renewal is a renewer by definition (same product only exists
        # when the licence renews), so its units due would be its renewed units and its rate always 100 %
        isolated_renewed_units_col="total_renewed_units_without_softcancel",
        isolated_renewed_usd_col="total_renewed_usd_without_softcancel",
        isolated_renewed_pipeline_usd_col="total_tr_usd_renewed_without_softcancel",
        # the dispersion of the isolated renewals (built per licence, summed): the second moment and six ratio bands
        isolated_renewed_usd_sq_over_tr_col="total_renewed_usd_sq_over_tr_isolated",
        isolated_tr_usd_renewed_lt095_col="total_tr_usd_renewed_isolated_lt095",
        isolated_tr_usd_renewed_095_100_col="total_tr_usd_renewed_isolated_095_100",
        isolated_tr_usd_renewed_100_105_col="total_tr_usd_renewed_isolated_100_105",
        isolated_tr_usd_renewed_105_110_col="total_tr_usd_renewed_isolated_105_110",
        isolated_tr_usd_renewed_110_120_col="total_tr_usd_renewed_isolated_110_120",
        isolated_tr_usd_renewed_ge120_col="total_tr_usd_renewed_isolated_ge120",
        ignore_cols=["dummy_field", "_filter2", "total_tr_units_without_softcancel"],   # [por confirmar] as in the 19-oct extract
        # the simulation window (current month → December): what happens in it falls due in 2027
        term_column="tr_term",
        one_year_term_value="1 year",
        acquisition_column="net_new",
        acquisition_values=["Acquisition_Not-New", "Acquisition_Pure-New"],
        renewed_acquisition_value="Retention_Not-New",      # an acquisition that renews: its next due date is a retention
        dims_after_renewal={"prev_OperationGroup": "Renewal"},   # after renewing, the previous operation is the renewal
        # a tariff changes by region (its three levels) and product: the price increases are detected per group
        price_group_dims=["tr_regional_level_1", "tr_regional_level_2", "tr_regional_level_3", "tr_product_level_1"],
        # the statistical uplift: the last 12 closed months (one price cycle), without the increases detected per group;
        # an increase still in its cycle is applied again to the future months inside it, then its effect is lost
        uplift_window_months=12,
        uplift_without_increases=True,
        acquisition_discount=0.4,
        # the acquisition team's targets of the year per subregion: sold + simulated = target (step 5.1)
        acquisition_targets_file=ACQUISITION_TARGETS_FILE,
        acquisition_target_column="tr_regional_level_3",
        acquisition_target_unit_usd=1000.0,
        # the time_series universe (retail to subscription): its region and its projection
        ts_region_columns=["tr_regional_level_1", "tr_regional_level_2", "tr_regional_level_3"],   # projected by country
        # the term transitions, once the extract brings their six columns (TERM_TRANSITION_COLUMNS_IN_EXTRACT)
        **(TERM_TRANSITION_COLUMNS if TERM_TRANSITION_COLUMNS_IN_EXTRACT else {}),
        term_transition_levels=TERM_TRANSITION_LEVELS,
        # the levers agreed with the business, when palancas.csv is there (step 7.2)
        levers_file=LEVERS_FILE if os.path.exists(LEVERS_FILE) else None,
    )


def synthetic_configuration() -> Config:
    """The synthetic raw of the tests: 2023-01..2026-12, current month 2026-09. Its tables
    go to a SQLite file in salida/."""
    os.makedirs(SYNTHETIC_OUTPUT_FOLDER, exist_ok=True)
    return SyntheticConfig(
        sql_engine=create_engine(f"sqlite:///{SYNTHETIC_DATABASE}"),
        current_month="2026-09",
        test_months=3,
        business_mandatory_dims=["region", "product"],
        structural_timevarying_dims={"dormant": "negative", "softcancel": "negative",
                                     "no_instalado": "negative", "autorenew": "positive"},
        extra_renovacion=["channel"],
        extra_revalorizacion=["newcust"],
        # the synthetic carries the exact discount as discount_pct and its own bucket as
        # discount: the framework derives the bucket, so the synthetic's is ignored
        discount_value_column="discount_pct",
        ignore_cols=["dataset_role", "is_current_month", "discount"],
        renewed_pipeline_usd_col="total_tr_usd_renewed",
        isolated_pipeline_units_col="total_tr_units_without_softcancel",
        isolated_renewed_units_col="total_renewed_units_without_softcancel",
        isolated_renewed_usd_col="total_renewed_usd_without_softcancel",
        isolated_renewed_pipeline_usd_col="total_tr_usd_renewed_without_softcancel",
        # the dispersion of the isolated renewals (built per licence, summed): the second moment and six ratio bands
        isolated_renewed_usd_sq_over_tr_col="total_renewed_usd_sq_over_tr_isolated",
        isolated_tr_usd_renewed_lt095_col="total_tr_usd_renewed_isolated_lt095",
        isolated_tr_usd_renewed_095_100_col="total_tr_usd_renewed_isolated_095_100",
        isolated_tr_usd_renewed_100_105_col="total_tr_usd_renewed_isolated_100_105",
        isolated_tr_usd_renewed_105_110_col="total_tr_usd_renewed_isolated_105_110",
        isolated_tr_usd_renewed_110_120_col="total_tr_usd_renewed_isolated_110_120",
        isolated_tr_usd_renewed_ge120_col="total_tr_usd_renewed_isolated_ge120",
        # the simulation window: acquisitions are newcust = 1
        acquisition_column="newcust",
        acquisition_values=[1],
        renewed_acquisition_value=0,
        price_group_dims=["region", "product"],
    )


def like_real_configuration(current_month: str = "2026-09") -> Config:
    """The synthetic that looks like the production extract (synthetic_real.py): the production columns and
    the Config of the run of 19-oct-2026 (exam of 6 months, uplift window of 12 months without increases).
    Its tables go to a SQLite file in salida/; compare_with_real.py puts its numbers next to the real ones."""
    os.makedirs(SYNTHETIC_OUTPUT_FOLDER, exist_ok=True)
    return LikeRealConfig(
        sql_engine=create_engine(f"sqlite:///{LIKE_REAL_DATABASE}"),
        current_month=current_month,
        test_months=6,
        business_mandatory_dims=["tr_regional_level_1", "tr_regional_level_2", "tr_regional_level_3",
                                 "tr_product_level_1", "tr_product_level_2", "tr_renewal_type", "tr_term", "tr_band",
                                 "tr_master_partner_code"],
        leveled_dims={"tr_term": "ordinal", "tr_band": "ordinal"},
        levels_path=LIKE_REAL_LEVELS,
        structural_timevarying_dims={"dormant": "negative", "softcancel": "negative", "not_installed": "negative"},
        # the synthetic says WHEN every softcancel was set: softcancel_month_0 … softcancel_month_12
        maturation_dims=["softcancel"],
        extra_renovacion=["net_new", "prev_OperationGroup"],
        discount_value_column="discount",
        sku_column="sku",
        extra_measure_cols=["total_reacquired_units", "total_reacquired_usd"],
        renewed_pipeline_usd_col="total_tr_usd_renewed",
        isolated_renewed_units_col="total_renewed_units_without_softcancel",
        isolated_renewed_usd_col="total_renewed_usd_without_softcancel",
        isolated_renewed_pipeline_usd_col="total_tr_usd_renewed_without_softcancel",
        isolated_renewed_usd_sq_over_tr_col="total_renewed_usd_sq_over_tr_isolated",
        isolated_tr_usd_renewed_lt095_col="total_tr_usd_renewed_isolated_lt095",
        isolated_tr_usd_renewed_095_100_col="total_tr_usd_renewed_isolated_095_100",
        isolated_tr_usd_renewed_100_105_col="total_tr_usd_renewed_isolated_100_105",
        isolated_tr_usd_renewed_105_110_col="total_tr_usd_renewed_isolated_105_110",
        isolated_tr_usd_renewed_110_120_col="total_tr_usd_renewed_isolated_110_120",
        isolated_tr_usd_renewed_ge120_col="total_tr_usd_renewed_isolated_ge120",
        ignore_cols=["dummy_field", "_filter2", "total_tr_units_without_softcancel"],
        term_column="tr_term",
        one_year_term_value="1 year",
        acquisition_column="net_new",
        acquisition_values=["Acquisition_Not-New", "Acquisition_Pure-New"],
        renewed_acquisition_value="Retention_Not-New",
        dims_after_renewal={"prev_OperationGroup": "Renewal"},
        price_group_dims=["tr_regional_level_1", "tr_regional_level_2", "tr_regional_level_3", "tr_product_level_1"],
        uplift_window_months=12,
        uplift_without_increases=True,
        acquisition_discount=0.4,
        ts_region_columns=["tr_regional_level_1", "tr_regional_level_2", "tr_regional_level_3"],
        **TERM_TRANSITION_COLUMNS,                       # the synthetic brings them (every licence renews to its own term)
        term_transition_levels=TERM_TRANSITION_LEVELS,
        # the levers agreed with the business, when palancas.csv is there (step 7.2)
        levers_file=LEVERS_FILE if os.path.exists(LEVERS_FILE) else None,
    )


# ═══════════════════════════════════════════════════════════════════════════════════
# THE RUN
# ═══════════════════════════════════════════════════════════════════════════════════

def run(configuration: Config, preparation=None) -> dict:
    """Every step, in the order of their dependencies (pipeline.py: contracts, step interface, orchestrator).

    preparation: a block 1 already run or resumed from SQL (block_1_preparation.PreparationBlock); the run then goes
    on from step 2.1. In a notebook:
        block = PreparationBlock(configuration).run()                 # steps 1.1 to 1.7, in memory
        block.persist_block()                                         # optional: to SQL
        block = PreparationBlock(configuration).resume_block_from_sql()   # another day: back from SQL
        results = run(configuration, preparation=block)"""
    return Orchestrator(configuration).run(preparation=preparation)


def stages_of_the_command_line(arguments: list) -> StagesToRun:
    """The switches of this file, changed by the words of the command line (sin_datos, sin_analisis, sin_aprender,
    escenario, solo_datos, solo_analisis, informe, referencia)."""
    stages = StagesToRun(data=RUN_STAGE_0_DATA, analysis=RUN_STAGE_1_ANALYSIS, learning=RUN_STAGE_2_LEARNING,
                         forecast=RUN_FORECAST, report=RUN_REPORT, report_questions=list(REPORT_QUESTIONS), kind=RUN_KIND,
                         note=RUN_NOTE)
    if SCENARIO_KEYWORD in arguments:
        stages.kind = "escenario"
    if REFERENCE_KEYWORD in arguments:
        stages.kind = "referencia"
    if SKIP_DATA_KEYWORD in arguments or SCENARIO_KEYWORD in arguments:
        stages.data = False
    if SKIP_ANALYSIS_KEYWORD in arguments or SCENARIO_KEYWORD in arguments:
        stages.analysis = False
    if SKIP_LEARNING_KEYWORD in arguments or SCENARIO_KEYWORD in arguments:
        stages.learning = False
    if ONLY_DATA_KEYWORD in arguments:
        stages.data, stages.analysis, stages.forecast, stages.report = True, False, False, False
    if ONLY_ANALYSIS_KEYWORD in arguments:
        stages.data, stages.analysis, stages.forecast, stages.report = False, True, False, False
    if REPORT_KEYWORD in arguments:
        stages.report = True
    return stages


if __name__ == "__main__":
    # python main.py [sintetico | parecido [YYYY-MM]] [sin_datos | sin_analisis | sin_aprender | escenario | solo_datos |
    #                solo_analisis] [informe] [referencia]
    arguments = sys.argv[1:]
    stage_words = {SKIP_DATA_KEYWORD, SKIP_ANALYSIS_KEYWORD, SKIP_LEARNING_KEYWORD, SCENARIO_KEYWORD, ONLY_DATA_KEYWORD,
                   ONLY_ANALYSIS_KEYWORD, REPORT_KEYWORD, REFERENCE_KEYWORD}
    if SYNTHETIC_KEYWORD in arguments:
        configuration = synthetic_configuration()
    elif LIKE_REAL_KEYWORD in arguments:
        months_given = [argument for argument in arguments if argument != LIKE_REAL_KEYWORD and argument not in stage_words]
        configuration = like_real_configuration(*months_given[:1])
    else:
        configuration = production_configuration()
    run_stages(configuration, stages_of_the_command_line(arguments))
