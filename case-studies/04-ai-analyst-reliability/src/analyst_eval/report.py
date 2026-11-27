"""Aggregate validated saved runs into results/summary.{json,md}."""

from __future__ import annotations

import json
from pathlib import Path

from analyst_eval import RESULTS_DIR
from analyst_eval.answer_key import load_answer_key
from analyst_eval.conditions import CONDITIONS
from analyst_eval.grading import grade_answer, summarize
from analyst_eval.runners import Pricing
from analyst_eval.runs import load_run

SUMMARY_JSON = RESULTS_DIR / "summary.json"
SUMMARY_MD = RESULTS_DIR / "summary.md"
PENDING = (
    "# Results\n\nNo live model runs have been recorded yet, so there are no results. "
    "See the case README for how to run the evaluation.\n"
)


def summarize_runs(paths: list[Path]) -> dict:
    key = load_answer_key()
    runs = []
    for p in paths:
        meta, answers, end = load_run(p)
        grades = [grade_answer(a, key[a["question_id"]]) for a in answers]
        pricing = Pricing(**meta["pricing"]) if meta.get("pricing") else None
        runs.append({
            "run_id": meta["run_id"], "file": p.name, "provider": meta["provider"],
            "model": meta["model"], "trials": meta["trials"],
            "stopped": (end or {}).get("stopped"),
            **summarize(grades, key, pricing),
        })
    return {"runs": runs}


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def render_markdown(summary: dict) -> str:
    if not summary["runs"]:
        return PENDING
    lines = ["# Results", ""]
    order = list(CONDITIONS)
    for run in summary["runs"]:
        lines += [f"## {run['provider']} / {run['model']} (`{run['file']}`)", ""]
        if run["stopped"]:
            lines += [f"> Run stopped early: {run['stopped']}.", ""]
        lines += [
            "| Condition | n | Accuracy | Materially correct (±1%) | Confidently wrong "
            "| Caveated wrong | Over-abstained "
            "| Matched naive answer | Lift vs no_context (95% CI) | Tokens in / out per q "
            "| Cost per q | Cost per correct |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        conds = sorted(run["conditions"], key=lambda c: order.index(c) if c in order else 99)
        for c in conds:
            r = run["conditions"][c]
            lift = r.get("accuracy_lift_vs_baseline")
            lift_s = (f"{100 * lift['mean']:+.1f} pp ({100 * lift['ci95'][0]:+.1f}, "
                      f"{100 * lift['ci95'][1]:+.1f})") if lift else "-"
            cost_q = r.get("cost_usd_per_q")
            cost_c = r.get("cost_usd_per_correct")
            lines.append(
                f"| {c} | {r['n_answers']} | {_pct(r['correct_rate'])} "
                f"| {_pct(r['materially_correct_rate'])} "
                f"| {_pct(r['confidently_wrong_rate'])} | {_pct(r['caveated_wrong_rate'])} "
                f"| {_pct(r['over_abstained_rate'])} | {_pct(r['fell_for_naive_rate'])} "
                f"| {lift_s} | {r['input_tokens_per_q']:.0f} / {r['output_tokens_per_q']:.0f} "
                f"| {'n/a' if cost_q is None else f'${cost_q:.4f}'} "
                f"| {'n/a' if cost_c is None else f'${cost_c:.4f}'} |"
            )
        traps = sorted({t for c in conds for t in run["conditions"][c]["accuracy_by_trap"]})
        lines += ["", "Accuracy by trap (questions where the trap is live):", "",
                  "| Trap | " + " | ".join(conds) + " |",
                  "|---|" + "---|" * len(conds)]
        for t in traps:
            cells = [_pct(run["conditions"][c]["accuracy_by_trap"].get(t)) for c in conds]
            lines.append(f"| {t} | " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)


def write_summary(paths: list[Path]) -> dict:
    summary = summarize_runs(paths)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    SUMMARY_MD.write_text(render_markdown(summary), encoding="utf-8")
    return summary
