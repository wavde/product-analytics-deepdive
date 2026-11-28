"""Aggregate validated saved runs into results/summary.{json,md}."""

from __future__ import annotations

import json
from pathlib import Path

from analyst_eval import RESULTS_DIR
from analyst_eval.answer_key import VARIANTS, load_answer_key, variant_of
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
    """One summary per (provider, model, variant), pooling every run file and trial.

    Files for the same model can hold different conditions (e.g. core conditions in one
    file, ablations in another) or different trials. A (condition, question, trial) that
    appears in more than one file is an error, not something to average. Runs against
    the holdout warehouse are graded against its own answer key and reported separately.
    """
    keys = {v: load_answer_key(spec["key"]) for v, spec in VARIANTS.items()
            if spec["key"].exists()}
    groups: dict[tuple[str, str, str], dict] = {}
    for p in paths:
        meta, answers, end = load_run(p)
        variant = variant_of(meta)
        g = groups.setdefault((meta["provider"], meta["model"], variant), {
            "provider": meta["provider"], "model": meta["model"], "variant": variant,
            "files": [], "runner_kind": meta.get("runner_kind", "api"), "stopped": [],
            "answers": [], "pricing": [],
        })
        g["files"].append(p.name)
        g["answers"] += answers
        g["pricing"].append(meta.get("pricing"))
        if (end or {}).get("stopped"):
            g["stopped"].append(f"{p.name}: {end['stopped']}")
    runs = []
    for g in groups.values():
        seen: dict[tuple, int] = {}
        for a in g["answers"]:
            k = (a["condition"], a["question_id"], int(a.get("trial", 0)))
            seen[k] = seen.get(k, 0) + 1
        dupes = sorted(k for k, n in seen.items() if n > 1)
        if dupes:
            raise ValueError(f"{g['model']}: answers recorded more than once: {dupes[:5]}")
        key = keys[g["variant"]]
        grades = [grade_answer(a, key[a["question_id"]]) for a in g["answers"]]
        prices = {json.dumps(x, sort_keys=True) for x in g["pricing"]}
        pricing = (Pricing(**g["pricing"][0]) if len(prices) == 1 and g["pricing"][0]
                   else None)
        runs.append({
            "provider": g["provider"], "model": g["model"], "variant": g["variant"],
            "files": sorted(g["files"]),
            "runner_kind": g["runner_kind"], "stopped": g["stopped"],
            "trials": sorted({k[2] for k in seen}),
            **summarize(grades, key, pricing),
        })
    runs.sort(key=lambda r: (r["variant"] != "main", r["variant"], r["provider"], r["model"]))
    return {"runs": runs}


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def render_markdown(summary: dict) -> str:
    if not summary["runs"]:
        return PENDING
    lines = ["# Results", ""]
    order = list(CONDITIONS)
    for run in summary["runs"]:
        files = ", ".join(f"`{f}`" for f in run["files"])
        where = ("" if run.get("variant", "main") == "main"
                 else f" — {run['variant']} warehouse (one undocumented trap)")
        lines += [f"## {run['provider']} / {run['model']}{where}", "",
                  f"Trials: {', '.join(str(t) for t in run['trials'])}. Files: {files}.", ""]
        for s in run["stopped"]:
            lines += [f"> Run stopped early: {s}.", ""]
        lines += [
            "| Condition | n | Accuracy | Materially correct (±1%) | Confidently wrong "
            "| Caveated wrong | Over-abstained "
            "| Matched naive answer | Lift vs no_context (95% CI) | Same outcome across trials "
            "| SQL calls per q | Tokens in / out per q | Cost per q | Cost per correct |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        conds = sorted(run["conditions"], key=lambda c: order.index(c) if c in order else 99)
        for c in conds:
            r = run["conditions"][c]
            lift = r.get("accuracy_lift_vs_baseline")
            lift_s = (f"{100 * lift['mean']:+.1f} pp ({100 * lift['ci95'][0]:+.1f}, "
                      f"{100 * lift['ci95'][1]:+.1f})") if lift else "-"
            cost_q = r.get("cost_usd_per_q")
            cost_c = r.get("cost_usd_per_correct")
            tokens = ("n/a" if not (r["input_tokens_per_q"] or r["output_tokens_per_q"])
                      else f"{r['input_tokens_per_q']:.0f} / {r['output_tokens_per_q']:.0f}")
            lines.append(
                f"| {c} | {r['n_answers']} | {_pct(r['correct_rate'])} "
                f"| {_pct(r['materially_correct_rate'])} "
                f"| {_pct(r['confidently_wrong_rate'])} | {_pct(r['caveated_wrong_rate'])} "
                f"| {_pct(r['over_abstained_rate'])} | {_pct(r['fell_for_naive_rate'])} "
                f"| {lift_s} | {_pct(r.get('same_outcome_across_trials'))} "
                f"| {r['sql_calls_per_q']:.1f} | {tokens} "
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
