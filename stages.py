"""
stages.py — The stages of SFF, run in order; every one can be left out (28-oct-2026, PLAN_etapas.md).

THE STAGES OF THE PLAN AND WHAT RUNS TODAY:
  0  data          stage_0_data.py      the pipeline read with its SQL, tested and written
  1  analysis      stage_1_analysis.py  the pipeline described before predicting it: tables sff_e1_*, charts and
                                        ANALISIS_pipeline.md (the descriptive parts still in the report and the
                                        data profile are noted for the refactoring, PLAN_etapas.md)
  2  learning      forecast_dynamics.py the forecast dynamics learned and persisted with their card (today: the maturation
                                        of the customer states, step 4.1); the rest are still learned in their blocks
  3  core          ┐ still inside the forecast (blocks 1 to 8): they come out of it one piece at a time,
  4  business      ┘ the forecast: pipeline.py (blocks 1 to 8) · the report: informe_forecast.py (chapters 1 to 9)
  5  monitoring    to do

WHAT EACH SWITCH DOES (StagesToRun):
  data       True    read the pipeline, test it and write it (stage 0). The forecast starts from it.
             False   the forecast reads the dataset written by the last stage 0: the SQL of the pipeline is not
                     run again. Within a month, every scenario after the first one runs like this.
  analysis   True    describe the pipeline (stage 1) on the dataset of stage 0 (built now, or the one written).
             False   no analysis: the scenarios of the month.
  learning   True    the forecast learns its dynamics and persists them (sff_fd_*).
             False   the forecast reads the dynamics persisted in this cut: what takes time to learn (the exam of the
                     maturation curve) is not done again. With data = False too: a scenario of the month.
  forecast   True    blocks 1 to 8 on the dataset: the tables sff_* of the run.
  report     True    the questions of informe_forecast.py over the tables in SQL (report_questions: some of them).
  kind, note         every forecast is registered (runs.py: sff_ejecuciones and the picture of its result) as a
                     baseline, an escenario or the referencia delivered to the business, which is also frozen.

A forecast without stage 0 and without a dataset written stops and says so. A forecast given a block 1
already run or resumed (preparation) does not need the dataset: it goes on from block 2.

THE INTERFACE:
  results = run_stages(configuration, StagesToRun(data=False))       the forecast on the persisted dataset
  results["analysis"]       the tables, the charts and the markdown of stage 1 (stage_1_analysis.py)
  results["forecast"]       the results of the forecast (as main.run gives them)
  results["report"]         {number: Answer} of the report
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import time
from dataclasses import dataclass, field

from config import Config
from pipeline import Orchestrator
from runs import freeze_the_reference, register_the_run
from stage_0_data import build_the_dataset, read_the_dataset
from stage_1_analysis import analyse_the_pipeline


@dataclass
class StagesToRun:
    """What to run, in order. Every switch is independent: data alone refreshes the dataset; forecast alone reads it."""
    data: bool = True                     # 0 · read the pipeline, test it and write it
    analysis: bool = True                 # 1 · describe the pipeline (sff_e1_*, ANALISIS_pipeline.md)
    learning: bool = True                 # 2 · learn the forecast dynamics and persist them (False: read the persisted ones)
    forecast: bool = True                 # blocks 1 to 8
    report: bool = False                  # informe_forecast.py
    report_questions: list = field(default_factory=list)    # [] = every question of the report
    kind: str = "baseline"                # the kind of run in the register (runs.py): baseline · escenario · referencia
    note: str = ""                        # a note for the register (what this run is: "campaña cancel DACH +3 pp")


def run_stages(configuration: Config, stages: StagesToRun = None, preparation=None) -> dict:
    """The stages asked for, in order (see the header). preparation: a block 1 already run or resumed from SQL."""
    stages = stages or StagesToRun()
    logger = configuration.logger
    results, seconds = {}, {}
    switches = (f"data {'yes' if stages.data else 'no (persisted dataset)'} · "
                f"analysis {'yes' if stages.analysis else 'no'} · "
                f"learning {'yes' if stages.learning else 'no (persisted dynamics)'} · "
                f"forecast {'yes' if stages.forecast else 'no'} · report {'yes' if stages.report else 'no'}")
    logger.doc(f"[ETAPAS] ══════════ SFF · stages of this run: {switches} ══════════")

    # stage 0 · the data: built now, or read as persisted (the analysis and the forecast need it)
    dataset = {}
    started = time.time()
    if stages.data:
        dataset["raw"] = build_the_dataset(configuration)
    elif stages.analysis or (stages.forecast and preparation is None):
        dataset["raw"] = read_the_dataset(configuration)
    seconds["0 data"] = time.time() - started

    # stage 1 · the analysis of the pipeline: tables, charts and the markdown; it keeps no row of the dataset
    if stages.analysis:
        started = time.time()
        results["analysis"] = analyse_the_pipeline(dataset["raw"], configuration)
        seconds["1 analysis"] = time.time() - started

    # the forecast (blocks 1 to 8). The extract is handed over with pop: no name here keeps it in memory while the
    # forecast runs (block 1 lets it go after step 1.1)
    if stages.forecast:
        started = time.time()
        results["forecast"] = Orchestrator(configuration).run(preparation=preparation, raw_extract=dataset.pop("raw", None),
                                                              learn_dynamics=stages.learning)
        seconds["forecast"] = time.time() - started
        # the register of runs: every forecast leaves its row and its picture; a reference is frozen
        results["run"] = register_the_run(configuration, stages.kind, stages.note, switches, seconds["forecast"])
        if stages.kind == "referencia" and results["run"]:
            results["reference"] = freeze_the_reference(configuration, results["run"]["run_id"], stages.note)
    dataset.clear()

    # the report (over the tables in SQL: the ones of this run, or of the last one)
    if stages.report:
        from informe_forecast import report
        started = time.time()
        results["report"] = report(configuration, stages.report_questions or None)
        seconds["report"] = time.time() - started

    logger.doc("[ETAPAS] time per stage: " + " · ".join(f"{name} {value:.0f}s" for name, value in seconds.items()
                                                       if name != "0 data" or stages.data or stages.forecast))
    return results
