"""
forecast_dynamics.py — STAGE 2 · THE FORECAST DYNAMICS: what the forecast learns from the data, persisted with its card,
so a scenario of the same month does not learn it again (28-oct-2026, PLAN_etapas.md, milestone H3).

MISSION: a forecast dynamic is a pattern the forecast learns from the past and applies to predict the future (a
maturation curve, a share of the term transitions, a calendar of price increases). We learn it from the past, the core
applies it in the present, and the monitoring (stage 5) confirms with the future whether it held. Learned once per cut,
it is persisted with a CARD that says when and from what it was learned; within the same cut, the forecast reads it
back instead of learning it again. Every dynamic keeps its method in its block: the same code learns it here, at the last closed month, and in the exam of
step 7.1, at the origin of every exam month ("learn as of X"), so the exam stays honest.

THE FIRST DYNAMIC: THE MATURATION OF THE CUSTOMER STATES (block 4, step 4.1)
  What is expensive in step 4.1 is not the box (StateMaturation learns its mix and its curves in seconds) but the EXAM
  of the curve of every dated state (every exam month × horizon learns a curve again: most of the time of the step)
  and the DECISION it takes: a curve that fails its exam is not used (rejected_maturation_dims). That is what is
  persisted, with what the box learned so it can be read in SQL:
    fd_maduracion_ficha        the card: cut, learned as of, the states, the dated states with their curve used or
                               rejected (and the errors that decided it), the fingerprint of the closed months it
                               learned from and of the fields of the Config the step reads
    fd_maduracion_examen       the exam of the curve of every dated state, by horizon (what the verdict and the report read)
    fd_maduracion_curva        the curve of the portfolio of every dated state: the share of the final state visible k
                               months before due, and p(k)
    fd_maduracion_por_region   the maturation of every state by region (action 3 of step 4.1)
  Reading it back (resume_the_maturation): the card must be of this cut, learned from the same closed months (same rows,
  units and units in every state) with the same fields of the Config and the same exam months; then the box is built
  again from the fine table (seconds, the same code) and takes the decision of the card. The curve is not examined
  again. A card that does not match stops the run and says what changed: learn again (stage 2).

THE INTERFACE:
  persist_the_maturation(box, fine_table, configuration)     after step 4.1 has learned (stage 2 run)
  box = resume_the_maturation(fine_table, configuration)     instead of step 4.1 (stage 2 not run)
"""

# ─── imports ─────────────────────────────────────────────────────────────────────
import datetime
import hashlib
import time
from dataclasses import fields as dataclass_fields

import numpy as np
import pandas as pd

from block_1_preparation import FIELDS_THAT_DO_NOT_CHANGE_THE_BLOCK, read_plain_table, write_plain_table
from block_4_customer_states import STEP_4_1_LABEL, StateMaturation
from config import (CALENDAR_ROLE_COLUMN, ROLE_TEST, TABLE_STAGE_2_MATURATION_BY_REGION, TABLE_STAGE_2_MATURATION_CARD,
                    TABLE_STAGE_2_MATURATION_CURVE, TABLE_STAGE_2_MATURATION_EXAM, Config, negative_states,
                    steps_reading_each_field)
from maturation import MaturationCurve, curve_history, is_in_state

# ─── named constants ─────────────────────────────────────────────────────────────
STAGE_2_LABEL = "E2"
STAGE_2_NAME = "FORECAST DYNAMICS"
MATURATION_DYNAMIC = "maduracion_estados"
MATURATION_METHOD_VERSION = "2026-10-28"          # the version of the method of step 4.1 the card was learned with
# fields of the Config step 4.1 reads that change nothing it learns (what it shows)
FIELDS_THAT_DO_NOT_CHANGE_THE_MATURATION = set(FIELDS_THAT_DO_NOT_CHANGE_THE_BLOCK) | {"maturation_regions_shown"}
EXAM_ATTRIBUTES = ("curve_error", "seen_error", "passes")      # the decision of the exam of a curve (its attrs)


# ═══════════════════════════════════════════════════════════════════════════════════
# WHAT THE DYNAMIC WAS LEARNED FROM
# ═══════════════════════════════════════════════════════════════════════════════════

def maturation_fingerprint(fine_table: pd.DataFrame, configuration: Config) -> dict:
    """What step 4.1 learns from: the closed months of its window (rows, units due, units in every state), the exam
    months, the current month and every field of the Config the step reads. Two runs with the same fingerprint learn
    the same box and take the same decision."""
    last_closed = configuration.calendar_boundaries()["current"] - 1
    history = curve_history(fine_table, configuration, up_to=last_closed)
    units = history[configuration.pipeline_units_col].to_numpy(dtype=float)
    months = sorted(history[configuration.period_col].unique())
    exam_months = sorted(fine_table.loc[fine_table[CALENDAR_ROLE_COLUMN] == ROLE_TEST, configuration.period_col].unique())
    fingerprint = {"corte": str(configuration.calendar_boundaries()["current"]),
                   "historia_meses": f"{months[0]}..{months[-1]}" if months else "",
                   "historia_filas": str(len(history)),
                   "historia_unidades": f"{units.sum():.6f}",
                   "meses_examen": ",".join(str(month) for month in exam_months)}
    for state in negative_states(configuration):
        if state in history.columns:
            fingerprint[f"historia_unidades_{state}"] = f"{(units * is_in_state(history, state)).sum():.6f}"
    for field_name in fields_the_maturation_reads(configuration):
        fingerprint[f"config.{field_name}"] = repr(getattr(configuration, field_name))
    return fingerprint


def fields_the_maturation_reads(configuration: Config) -> list:
    """The fields of the Config the code of step 4.1 reads (block 4 and maturation.py), but the ones that only say
    where to write or what to show."""
    names = [config_field.name for config_field in dataclass_fields(type(configuration))]
    readers = steps_reading_each_field(names)
    return sorted(name for name, labels in readers.items()
                  if {"4.1", "B4"} & set(labels) and name not in FIELDS_THAT_DO_NOT_CHANGE_THE_MATURATION)


def fingerprint_hash(fingerprint: dict) -> str:
    text = "\n".join(f"{key}={value}" for key, value in sorted(fingerprint.items()))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ═══════════════════════════════════════════════════════════════════════════════════
# PERSIST (stage 2 run: step 4.1 has learned)
# ═══════════════════════════════════════════════════════════════════════════════════

def persist_the_maturation(box: StateMaturation, fine_table: pd.DataFrame, configuration: Config) -> dict:
    """The decision and what step 4.1 learned, with its card. Returns the card."""
    started = time.time()
    fingerprint = maturation_fingerprint(fine_table, configuration)
    exams = getattr(box, "curve_exams", {}) or {}
    card = {"dinamica": MATURATION_DYNAMIC, "version_metodo": MATURATION_METHOD_VERSION,
            "corte": fingerprint["corte"], "aprendido_a_fecha": str(box.as_of),
            "escrito": datetime.datetime.now().isoformat(timespec="seconds"),
            "estados": ",".join(box.states), "caja_identidad": str(bool(box.identity)),
            "estados_fechados": ",".join(exams),
            "curvas_usadas": ",".join(box.curves),
            "curvas_rechazadas": ",".join(configuration.rejected_maturation_dims),
            "huella": fingerprint_hash(fingerprint)}
    for state, exam in exams.items():
        for attribute in EXAM_ATTRIBUTES:
            card[f"examen.{state}.{attribute}"] = repr(exam.attrs.get(attribute))
    card.update({f"huella.{key}": value for key, value in fingerprint.items()})
    write_plain_table(pd.DataFrame(list(card.items()), columns=["clave", "valor"]), TABLE_STAGE_2_MATURATION_CARD, configuration)
    exam_table = (pd.concat([exam.assign(estado=state) for state, exam in exams.items()], ignore_index=True)
                  if exams else pd.DataFrame(columns=["estado", "h"]))
    write_plain_table(exam_table, TABLE_STAGE_2_MATURATION_EXAM, configuration)
    curves = [MaturationCurve(curve_history(fine_table, configuration, up_to=box.as_of), state, configuration)
              .portfolio_table().assign(estado=state, usada=state in box.curves)
              for state in exams] if not box.identity else []
    write_plain_table(pd.concat(curves, ignore_index=True) if curves else pd.DataFrame(columns=["estado", "meses_antes"]),
                      TABLE_STAGE_2_MATURATION_CURVE, configuration)
    by_region = box.maturation_by_region if box.maturation_by_region is not None else pd.DataFrame(columns=["estado"])
    write_plain_table(by_region, TABLE_STAGE_2_MATURATION_BY_REGION, configuration)
    configuration.logger.doc(f"[{STAGE_2_LABEL}] forecast dynamic '{MATURATION_DYNAMIC}' persisted in "
                             f"{configuration.table_prefix}{TABLE_STAGE_2_MATURATION_CARD} ({time.time() - started:.1f}s): "
                             f"cut {card['corte']}, learned as of {card['aprendido_a_fecha']}, curves used "
                             f"{card['curvas_usadas'] or '—'}, rejected {card['curvas_rechazadas'] or '—'}")
    return card


# ═══════════════════════════════════════════════════════════════════════════════════
# RESUME (stage 2 not run: the forecast reads the dynamic)
# ═══════════════════════════════════════════════════════════════════════════════════

def resume_the_maturation(fine_table: pd.DataFrame, configuration: Config) -> StateMaturation:
    """The box of step 4.1 with the decision of the persisted dynamic: built again from the fine table (the same code,
    seconds), its curves the ones the card used, its exam the one of the card. Stops when there is no dynamic or its
    card does not match this run (another cut, other closed months, another Config, other exam months)."""
    started = time.time()
    check_log = []
    configuration.log_step_start(STAGE_2_LABEL, f"{STAGE_2_NAME} · {MATURATION_DYNAMIC}",
                                 "read the maturation of the customer states learned by the last stage 2 of this cut, "
                                 "instead of learning it again (step 4.1)",
                                 ["read the card", "check it was learned from what this run would learn from",
                                  "build the box with its decision", "count the checks; stop if any failed"],
                                 "the box (StateMaturation) for step 7.2, with the exam and the decision of the card")
    try:
        card_table = read_plain_table(TABLE_STAGE_2_MATURATION_CARD, configuration)
    except Exception as error:
        raise ValueError(f"no persisted forecast dynamic '{MATURATION_DYNAMIC}' "
                         f"({configuration.table_prefix}{TABLE_STAGE_2_MATURATION_CARD}): run stage 2 first "
                         f"(RUN_STAGE_2_LEARNING = True in main.py) · {type(error).__name__}: {error}") from error
    card = dict(zip(card_table["clave"].astype(str), card_table["valor"].astype(str).replace("nan", "")))
    configuration.log_action(STAGE_2_LABEL, 1, f"card of '{card.get('dinamica')}': cut {card.get('corte')}, learned as of "
                                               f"{card.get('aprendido_a_fecha')} on {card.get('escrito')}")

    # [2] learned from what this run would learn from
    now = maturation_fingerprint(fine_table, configuration)
    changed = {key: (card.get(f"huella.{key}", "(absent)"), value) for key, value in now.items()
               if card.get(f"huella.{key}") != value}
    changed.update({key[len("huella."):]: (value, "(absent)") for key, value in card.items()
                    if key.startswith("huella.") and key[len("huella."):] not in now})
    detail = "; ".join(f"{key}: learned with {before} · now {after}" for key, (before, after) in sorted(changed.items()))
    configuration.log_check(STAGE_2_LABEL, check_log, "the dynamic was learned from what this run would learn from "
                            "(cut, closed months, exam months, Config)", not changed,
                            failure_detail=f"{len(changed)} differences: {detail[:1500]} · learn it again (stage 2)",
                            context=f"fingerprint {card.get('huella')}")
    configuration.log_check(STAGE_2_LABEL, check_log, "the dynamic was learned with the method of this version",
                            card.get("version_metodo") == MATURATION_METHOD_VERSION,
                            failure_detail=f"learned with the method of {card.get('version_metodo')}, this one is "
                                           f"{MATURATION_METHOD_VERSION}: learn it again (stage 2)")
    configuration.log_action(STAGE_2_LABEL, 4, "counting the checks")
    configuration.log_check_summary(STAGE_2_LABEL, f"{STAGE_2_NAME} · {MATURATION_DYNAMIC}", check_log)

    # [3] the box, with the decision of the card: the rejected curves are not built (maturation_dims_in_use)
    configuration.rejected_maturation_dims = [state for state in card.get("curvas_rechazadas", "").split(",") if state]
    last_closed = configuration.calendar_boundaries()["current"] - 1
    box = StateMaturation(fine_table, last_closed, configuration)
    box.curve_exams = exams_of_the_card(card, configuration)
    by_region = read_plain_table(TABLE_STAGE_2_MATURATION_BY_REGION, configuration)
    box.maturation_by_region = by_region if len(by_region) else None
    used = ",".join(box.curves)
    if used != card.get("curvas_usadas", ""):
        raise ValueError(f"the box built again uses the curves '{used}' and the card says '{card.get('curvas_usadas')}': "
                         f"learn the dynamic again (stage 2)")
    configuration.log_action(STAGE_2_LABEL, 3, f"the box at {last_closed}: {box.describe()} · rejected "
                                               f"{', '.join(configuration.rejected_maturation_dims) or '—'} (decision of "
                                               f"the card: the curve is not examined again) · {time.time() - started:.1f}s")
    configuration.logger.doc(f"[{STEP_4_1_LABEL}] step 4.1 not run: its box comes from the forecast dynamic of "
                             f"{card.get('escrito')} (the exam of the curve, its charts and its maturation by region "
                             f"are the ones of that run)")
    return box


def exams_of_the_card(card: dict, configuration: Config) -> dict:
    """The exam of the curve of every dated state, as step 4.1 left it ({state: one row per h}, its decision in attrs)."""
    table = read_plain_table(TABLE_STAGE_2_MATURATION_EXAM, configuration)
    exams = {}
    for state in [state for state in card.get("estados_fechados", "").split(",") if state]:
        exam = table[table["estado"].astype(str) == state].drop(columns=["estado"]).reset_index(drop=True)
        for column in exam.columns:                  # a CSV gives every value back as text
            exam[column] = pd.to_numeric(exam[column])
        exam.attrs["passes"] = card.get(f"examen.{state}.passes") == "True"
        for attribute in ("curve_error", "seen_error"):
            text = card.get(f"examen.{state}.{attribute}", "")
            exam.attrs[attribute] = float(text) if text not in ("", "None") else np.nan
        exams[state] = exam
    return exams
