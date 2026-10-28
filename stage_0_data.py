"""
stage_0_data.py — STAGE 0 · THE DATA: the pipeline read with its SQL, tested and written, ready to use (28-oct-2026).

MISSION: leave the pipeline of the current month read, tested and written, so everything computed that month comes
from the same data. The pipeline is the past pipeline with its result (what renewed) and the future pipeline, still
without a result.

WHAT IT DOES:
  build_the_dataset   reads the pipeline with the Config's read_raw (in production, the SQL of entorno_local.py from
                      Python), tests that it has what the framework needs (step 1.1: every column has a role and the
                      months hold the calendar; step 1.2: the values of the universes, money without nulls or
                      negatives, renewals coherent with what fell due, dimensions never empty, flags 0 / 1) and writes
                      it. A failed test stops the stage before anything is written.
  read_the_dataset    the dataset written by the last stage 0, every column with its type: the forecast, its scenarios
                      and the report of the month start from it without running the SQL again.

WHAT IT WRITES (table_prefix + …; CSV in output_folder without an engine):
  e0_dataset                the pipeline exactly as it was read (same rows, columns and values)
  e0_dataset_manifiesto     every column and its type, so every column comes back with its type

THE INTERFACE:
  raw = build_the_dataset(configuration)      read, test, write (stage 0)
  raw = read_the_dataset(configuration)       the dataset written by the last stage 0
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import time

import pandas as pd

from block_1_preparation import (check_the_values, frame_for_sql, frame_from_sql, read_plain_table, separate_the_universes,
                                 validate_raw, write_plain_table)
from config import TABLE_STAGE_0_DATASET, TABLE_STAGE_0_MANIFEST, Config

# ─── named constants ─────────────────────────────────────────────────────────────
STAGE_0_LABEL = "E0"
STAGE_0_NAME = "DATASET"
STAGE_0_PURPOSE = ("read the pipeline with its SQL, test that it has what the framework needs (steps 1.1 and 1.2) and "
                   "write it, so the forecast, its scenarios and the report of the month start from the same data")
STAGE_0_ACTIONS = ["read the pipeline (read_raw of the Config: the SQL of entorno_local.py in production)",
                   "test its structure: step 1.1",
                   "test its values: the universes and the values of step 1.2; stop if any failed",
                   "write the dataset and the type of every column"]
STAGE_0_OUTPUT = "sff_e0_dataset, sff_e0_dataset_manifiesto"
MANIFEST_COLUMNS = ["tabla", "posicion", "columna", "dtype", "tipo"]


# ═══════════════════════════════════════════════════════════════════════════════════
# BUILD THE DATASET (stage 0)
# ═══════════════════════════════════════════════════════════════════════════════════

def build_the_dataset(configuration: Config) -> pd.DataFrame:
    """Stage 0: read the pipeline, test it and write it. Returns the pipeline as it was read."""
    configuration.log_block_start(STAGE_0_LABEL, 0, STAGE_0_NAME, STAGE_0_PURPOSE)
    configuration.log_step_start(STAGE_0_LABEL, STAGE_0_NAME, STAGE_0_PURPOSE, STAGE_0_ACTIONS, STAGE_0_OUTPUT)
    check_log = []

    # [1] the pipeline, read from the source
    started = time.time()
    raw = configuration.read_raw()
    configuration.log_action(STAGE_0_LABEL, 1, f"pipeline read: {len(raw):,} rows × {len(raw.columns)} columns "
                                               f"({time.time() - started:.1f}s)")

    # [2] its structure: the checks of step 1.1 (they stop the stage if one fails)
    validated = validate_raw(raw, configuration)

    # [3] its values: the universes and the checks of the values of step 1.2; a failed one stops the stage here
    renewal_raw, time_series_rows = separate_the_universes(validated, configuration, check_log)
    check_the_values(renewal_raw, configuration, check_log)
    del validated, renewal_raw, time_series_rows
    configuration.log_check_summary(STAGE_0_LABEL, STAGE_0_NAME, check_log)

    # [4] the dataset, and the type of every column so it comes back as it was read
    started = time.time()
    sql_frame, manifest_rows = frame_for_sql(raw, TABLE_STAGE_0_DATASET)
    write_plain_table(sql_frame, TABLE_STAGE_0_DATASET, configuration)
    del sql_frame
    write_plain_table(pd.DataFrame(manifest_rows, columns=MANIFEST_COLUMNS), TABLE_STAGE_0_MANIFEST, configuration)
    configuration.log_action(STAGE_0_LABEL, 4, f"dataset written in {configuration.table_prefix}{TABLE_STAGE_0_DATASET} "
                                               f"({time.time() - started:.1f}s)")
    return raw


# ═══════════════════════════════════════════════════════════════════════════════════
# READ THE DATASET (stage 0 not run in this session)
# ═══════════════════════════════════════════════════════════════════════════════════

def read_the_dataset(configuration: Config) -> pd.DataFrame:
    """The dataset written by the last stage 0, every column with its type. Stops when there is none."""
    started = time.time()
    try:
        manifest = read_plain_table(TABLE_STAGE_0_MANIFEST, configuration)
        dataset = read_plain_table(TABLE_STAGE_0_DATASET, configuration)
    except Exception as error:
        raise ValueError(f"no dataset written ({configuration.table_prefix}{TABLE_STAGE_0_DATASET}): run stage 0 first "
                         f"(RUN_STAGE_0_DATA = True in main.py) · {type(error).__name__}: {error}") from error
    manifest["posicion"] = pd.to_numeric(manifest["posicion"]).astype(int)       # a CSV gives it back as text
    raw = frame_from_sql(dataset, manifest[manifest["tabla"] == TABLE_STAGE_0_DATASET])
    configuration.logger.doc(f"[{STAGE_0_LABEL}] dataset read from {configuration.table_prefix}{TABLE_STAGE_0_DATASET} "
                             f"({len(raw):,} rows × {len(raw.columns)} columns, {time.time() - started:.1f}s): the "
                             f"SQL of the pipeline is not run again")
    return raw
