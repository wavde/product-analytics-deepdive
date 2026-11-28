"""Grade answers against the answer key and aggregate by condition.

Outcomes for one answer:

* ``correct``          -- expected a number and got it within tolerance, or expected an
                          abstention and got one.
* ``confidently_wrong``-- status ``answered`` (no caveat) and not correct. This is the
                          error that reaches a decision unchallenged.
* ``caveated_wrong``   -- status ``answered_with_caveat`` and not correct.
* ``over_abstained``   -- abstained on an answerable question.
* ``no_answer``        -- protocol failure (no parseable final answer).

Strict tolerances are tight on purpose (exact counts, a dollar, 0.05 points). A secondary
"materially correct" rate also accepts answers within 1% of gold, to separate errors that
would change a decision from ones that would only fail a reconciliation.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from analyst_eval.questions import TOLERANCE
from analyst_eval.runners import Pricing

OUTCOMES = ("correct", "confidently_wrong", "caveated_wrong", "over_abstained", "no_answer")


@dataclass
class Grade:
    question_id: str
    condition: str
    trial: int
    outcome: str
    fell_for_naive: bool
    unit_slip: bool
    input_tokens: int
    output_tokens: int
    sql_calls: int
    material_ok: bool = False

    @property
    def correct(self) -> bool:
        return self.outcome == "correct"


MATERIALITY = 0.01  # within 1% of gold is "materially right" even if outside strict tolerance


def _close(a: float | None, b: float | None, tol: float) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


def grade_answer(answer: dict, key_row: dict) -> Grade:
    status = answer["status"]
    value = answer.get("value")
    tol = TOLERANCE.get(key_row["unit"] or "", 0.0)
    expect_abstain = key_row["expect_abstain"]

    if status == "no_answer":
        outcome = "no_answer"
    elif expect_abstain:
        if status == "abstained":
            outcome = "correct"
        else:
            outcome = "confidently_wrong" if status == "answered" else "caveated_wrong"
    elif status == "abstained":
        outcome = "over_abstained"
    elif _close(value, key_row["gold"], tol):
        outcome = "correct"
    else:
        outcome = "confidently_wrong" if status == "answered" else "caveated_wrong"

    wrong_number = outcome in ("confidently_wrong", "caveated_wrong") and value is not None
    gold = key_row["gold"]
    material_ok = outcome == "correct" or (
        not expect_abstain and status != "abstained" and gold is not None
        and _close(value, gold, max(tol, abs(gold) * MATERIALITY)))
    return Grade(
        question_id=answer["question_id"],
        condition=answer["condition"],
        trial=int(answer.get("trial", 0)),
        outcome=outcome,
        fell_for_naive=wrong_number and _close(value, key_row.get("naive"), tol),
        unit_slip=wrong_number and gold is not None
        and (_close(value / 100, gold, tol) or _close(value * 100, gold, tol)),
        input_tokens=int(answer.get("input_tokens", 0)),
        output_tokens=int(answer.get("output_tokens", 0)),
        sql_calls=int(answer.get("sql_calls", 0)),
        material_ok=material_ok,
    )


def paired_bootstrap_diff(
    a: dict[str, float], b: dict[str, float], n_boot: int = 5000, seed: int = 0
) -> tuple[float, float, float]:
    """Mean of (b - a) over shared questions with a percentile 95% CI, resampling questions."""
    ids = sorted(set(a) & set(b))
    if not ids:
        return (float("nan"),) * 3
    d = np.array([b[i] - a[i] for i in ids])
    rng = np.random.default_rng(seed)
    boots = d[rng.integers(0, len(d), size=(n_boot, len(d)))].mean(axis=1)
    return float(d.mean()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def summarize(
    grades: list[Grade], key: dict[str, dict], pricing: Pricing | None = None,
    baseline: str = "no_context",
) -> dict:
    by_cond: dict[str, list[Grade]] = defaultdict(list)
    for g in grades:
        by_cond[g.condition].append(g)

    def per_question_acc(gs: list[Grade]) -> dict[str, float]:
        acc: dict[str, list[bool]] = defaultdict(list)
        for g in gs:
            acc[g.question_id].append(g.correct)
        return {q: float(np.mean(v)) for q, v in acc.items()}

    base_acc = per_question_acc(by_cond.get(baseline, []))
    out: dict = {"conditions": {}}
    for cond, gs in by_cond.items():
        n = len(gs)
        counts = {o: sum(g.outcome == o for g in gs) for o in OUTCOMES}
        tin = sum(g.input_tokens for g in gs)
        tout = sum(g.output_tokens for g in gs)
        row = {
            "n_answers": n,
            "n_questions": len({g.question_id for g in gs}),
            **{f"{o}_rate": counts[o] / n for o in OUTCOMES},
            "materially_correct_rate": sum(g.material_ok for g in gs) / n,
            "fell_for_naive_rate": sum(g.fell_for_naive for g in gs) / n,
            "unit_slip_rate": sum(g.unit_slip for g in gs) / n,
            "input_tokens_per_q": tin / n,
            "output_tokens_per_q": tout / n,
            "sql_calls_per_q": sum(g.sql_calls for g in gs) / n,
        }
        if pricing:
            cost = pricing.cost(tin, tout)
            row["cost_usd_per_q"] = cost / n
            row["cost_usd_per_correct"] = cost / counts["correct"] if counts["correct"] else None
        by_cat: dict[str, list[bool]] = defaultdict(list)
        by_trap: dict[str, list[bool]] = defaultdict(list)
        for g in gs:
            k = key[g.question_id]
            by_cat[k["category"]].append(g.correct)
            for t in k["traps"]:
                by_trap[t].append(g.correct)
        row["accuracy_by_category"] = {c: float(np.mean(v)) for c, v in sorted(by_cat.items())}
        row["accuracy_by_trap"] = {t: float(np.mean(v)) for t, v in sorted(by_trap.items())}
        if cond != baseline and base_acc:
            mean, lo, hi = paired_bootstrap_diff(base_acc, per_question_acc(gs))
            row["accuracy_lift_vs_baseline"] = {"mean": mean, "ci95": [lo, hi]}
        out["conditions"][cond] = row
    return out
