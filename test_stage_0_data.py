"""
test_stage_0_data.py — Stage 0 (the data) and the stages of main: the pipeline read, tested and written; the written
dataset is the pipeline; the forecast on it is the forecast on the pipeline read again.

A · stage 0 builds the dataset: its two tables and the tests of steps 1.1 and 1.2; a failed test writes nothing
B · the written dataset comes back as the pipeline: every column with its type, every value
C · the forecast on the written dataset = the forecast on the pipeline read again (by month, by year, the exam)
D · no dataset written: the forecast stops and says what to do
E · the stages of main: data only builds the dataset and runs no block; the words of the command line change the
    switches; without an SQL engine the dataset goes to CSV

    python test_stage_0_data.py
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import os
import tempfile

import pandas as pd

from config import TABLE_STAGE_0_DATASET, TABLE_STAGE_0_MANIFEST
from main import SyntheticConfig, stages_of_the_command_line
from pipeline import Orchestrator
from stage_0_data import build_the_dataset, read_the_dataset
from stages import StagesToRun, run_stages
from test_helpers import check, check_stops, console_of, finish, synthetic_with


def same_frame(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    """The same columns, types, index and values (a missing value equals a missing value)."""
    try:
        pd.testing.assert_frame_equal(left, right, check_dtype=True, check_index_type=True)
        return True
    except AssertionError as difference:
        print(f"       {str(difference)[:300]}")
        return False


class NegativeMoneyConfig(SyntheticConfig):
    """The synthetic pipeline with a negative USD due in one row: a value step 1.2 refuses."""
    def read_raw(self) -> pd.DataFrame:
        raw = super().read_raw()
        raw.loc[raw.index[0], "total_tr_usd"] = -1.0
        return raw


def configuration_of(configuration_class, **overrides):
    """A Config of the synthetic with another class (another read_raw), the fields of synthetic_with."""
    base = synthetic_with(**overrides)
    arguments = {name: getattr(base, name) for name in base.__dataclass_fields__}
    return configuration_class(**arguments)


def tables_of(configuration) -> set:
    from sqlalchemy import inspect
    return set(inspect(configuration.sql_engine).get_table_names())


def test_stage_0_builds_the_dataset() -> None:
    print("A · stage 0 builds the dataset")
    configuration = synthetic_with()
    result = {}
    console = console_of(lambda: result.update(raw=build_the_dataset(configuration)))
    prefix = configuration.table_prefix
    written = {f"{prefix}{name}" for name in (TABLE_STAGE_0_DATASET, TABLE_STAGE_0_MANIFEST)}
    check(written <= tables_of(configuration), f"its two tables are written: {sorted(written)}")
    check("STEP 1.1 · VALIDATE RAW" in console and "dataset written" in console,
          "it tests the structure (step 1.1) and the values (step 1.2), then writes the dataset")
    refused = configuration_of(NegativeMoneyConfig)
    check_stops(lambda: build_the_dataset(refused), "", "a pipeline with a negative USD due stops at the tests")
    check(f"{prefix}{TABLE_STAGE_0_DATASET}" not in tables_of(refused), "and nothing is written")


def test_the_dataset_comes_back_as_the_pipeline() -> None:
    print("B · the written dataset comes back as the pipeline")
    configuration = synthetic_with()
    built = {}
    console_of(lambda: built.update(raw=build_the_dataset(configuration)))
    back = {}
    console = console_of(lambda: back.update(raw=read_the_dataset(configuration)))
    check(same_frame(built["raw"], back["raw"]), f"every column with its type and every value "
                                                f"({len(back['raw']):,} rows × {len(back['raw'].columns)} columns)")
    check("the SQL of the pipeline is not run again" in console, "read from its table: the SQL is not run again")


def test_the_forecast_on_the_dataset_is_the_forecast() -> None:
    print("C · the forecast on the written dataset = the forecast on the pipeline")
    on_the_pipeline = {}
    console_of(lambda: on_the_pipeline.update(Orchestrator(synthetic_with()).run()))
    configuration = synthetic_with()
    console_of(lambda: build_the_dataset(configuration))
    on_the_dataset = {}
    written = synthetic_with(sql_engine=configuration.sql_engine)
    console = console_of(lambda: on_the_dataset.update(run_stages(written, StagesToRun(data=False))))
    forecast_pipeline, forecast_dataset = on_the_pipeline["forecast"], on_the_dataset["forecast"]["forecast"]
    check("[main] ═══ SFF · reading the raw ═══" not in console and "the SQL of the pipeline is not run again" in console,
          "the forecast without stage 0 does not read the pipeline: it reads the dataset")
    check(same_frame(forecast_pipeline["by_month"], forecast_dataset["by_month"])
          and same_frame(forecast_pipeline["by_year"], forecast_dataset["by_year"]),
          f"the forecast by month and by year is the same (${forecast_pipeline['by_year']['total_usd'].sum():,.0f})")
    check(same_frame(on_the_pipeline["series_exam"]["summary"], on_the_dataset["forecast"]["series_exam"]["summary"]),
          "the exam is the same")


def test_no_dataset() -> None:
    print("D · no dataset written")
    check_stops(lambda: read_the_dataset(synthetic_with()), "run stage 0 first",
                "no dataset written: it stops and says what to do")


def test_the_stages_of_main() -> None:
    print("E · the stages of main")
    configuration = synthetic_with()
    results = {}
    console = console_of(lambda: results.update(run_stages(configuration, StagesToRun(data=True, forecast=False))))
    check("forecast" not in results and "dataset written" in console and "STEP 2.1 ·" not in console,
          "data only: the dataset is built and no block runs")
    check(stages_of_the_command_line(["parecido", "sin_datos"]).data is False
          and stages_of_the_command_line(["solo_datos"]).forecast is False
          and stages_of_the_command_line(["informe"]).report is True,
          "the words of the command line: sin_datos, solo_datos, informe")
    folder = tempfile.mkdtemp()
    without_engine = synthetic_with(sql_engine=None, output_folder=folder)
    built = {}
    console_of(lambda: built.update(raw=build_the_dataset(without_engine)))
    back = {}
    console_of(lambda: back.update(raw=read_the_dataset(without_engine)))
    check(os.path.exists(os.path.join(folder, f"{without_engine.table_prefix}{TABLE_STAGE_0_DATASET}.csv"))
          and same_frame(built["raw"], back["raw"]),
          "without an SQL engine the dataset goes to CSV and comes back from it as it was read")


if __name__ == "__main__":
    test_stage_0_builds_the_dataset()
    test_the_dataset_comes_back_as_the_pipeline()
    test_the_forecast_on_the_dataset_is_the_forecast()
    test_no_dataset()
    test_the_stages_of_main()
    finish()
