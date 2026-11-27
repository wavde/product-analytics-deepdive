"""Evidence for the case README: every number in the memo's cited sections comes from here.

Built deterministically from the warehouse and the answer key -- no model output. Each
entry records the value, how it was computed, and which checks it passed, following the
cited-memo skill.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from analyst_eval import DB_PATH, RESULTS_DIR
from analyst_eval.answer_key import ANSWER_KEY_PATH, load_answer_key
from analyst_eval.gold import Fixes

EVIDENCE_PATH = RESULTS_DIR / "evidence.json"
KEY_CHECKS = [
    "gold computed through views implementing every ground rule in definitions.md",
    "answer key regenerated from a fresh warehouse build and compared in CI",
]


def _entry(value: float, how: str, checks: list[str]) -> dict:
    return {"value": round(float(value), 4), "how": how, "checks": checks}


def build_evidence(db_path: Path | str = DB_PATH, key_path: Path = ANSWER_KEY_PATH) -> dict:
    key = load_answer_key(key_path)
    ev: dict[str, dict] = {}

    cats = [r["category"] for r in key.values()]
    ev["n_questions"] = _entry(len(key), "rows in answer_key.json", ["count"])
    for c in ("control", "trap", "ambiguous", "unanswerable"):
        ev[f"n_{c}"] = _entry(cats.count(c), f"questions with category={c}", ["count"])

    answerable = [r for r in key.values() if not r["expect_abstain"]]
    naive_wrong = [r for r in answerable if r["naive_is_wrong"]]
    ev["naive_wrong_answerable"] = _entry(
        len(naive_wrong), "answerable questions where the naive query misses tolerance",
        KEY_CHECKS)
    ev["naive_wrong_controls"] = _entry(
        sum(r["naive_is_wrong"] for r in answerable if r["category"] == "control"),
        "control questions where the naive query misses tolerance", KEY_CHECKS)
    non_control = [r for r in answerable if r["category"] != "control"]
    ev["naive_wrong_non_control_pct"] = _entry(
        100 * sum(r["naive_is_wrong"] for r in non_control) / len(non_control),
        "percent of trap+ambiguous questions the naive query gets wrong", KEY_CHECKS)
    ev["n_non_control_answerable"] = _entry(
        len(non_control), "trap + ambiguous questions", ["count"])
    ev["naive_material_wrong_non_control"] = _entry(
        sum(abs(r["naive"] - r["gold"]) > abs(r["gold"]) * 0.01 for r in non_control),
        "trap+ambiguous questions where the naive answer is more than 1% from gold",
        KEY_CHECKS)

    for t in sorted(Fixes.names()) + ["refunds", "partial_period", "units", "definition",
                                      "not_instrumented"]:
        ev[f"live_{t}"] = _entry(
            sum(t in r["traps"] for r in key.values()),
            f"questions tagged {t}"
            + (" (measured by disabling only this rule)" if t in Fixes.names() else ""),
            KEY_CHECKS)

    for qid, r in key.items():
        if r["gold"] is not None:
            ev[f"{qid}.gold"] = _entry(r["gold"], f"gold_sql for {qid}", KEY_CHECKS)
        if r["naive"] is not None:
            ev[f"{qid}.naive"] = _entry(r["naive"], f"naive_sql for {qid}", KEY_CHECKS)
        if r["gold"] and r["naive"] is not None:
            ev[f"{qid}.naive_error_pct"] = _entry(
                100 * (r["naive"] - r["gold"]) / r["gold"], f"(naive - gold) / gold for {qid}",
                KEY_CHECKS)
            ev[f"{qid}.naive_over_gold_x"] = _entry(
                r["naive"] / r["gold"], f"naive / gold for {qid}", KEY_CHECKS)

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        con.execute("SET TimeZone = 'UTC'")
        rows, distinct = con.execute(
            "SELECT COUNT(*), COUNT(DISTINCT event_id) FROM events WHERE event_name IN "
            "('view_product', 'add_to_cart', 'checkout', 'purchase')").fetchone()
        ev["retry_row_pct"] = _entry(
            100 * (rows - distinct) / distinct,
            "extra rows per 100 logical user-initiated events", ["COUNT(*) vs COUNT(DISTINCT)"])
        qa, organic = con.execute(
            """
            WITH o AS (
                SELECT DISTINCT e.order_id, u.is_internal,
                       CAST(e.event_ts AT TIME ZONE 'UTC' AT TIME ZONE 'America/Los_Angeles'
                            AS DATE) AS d
                FROM events e JOIN users u USING (user_id)
                WHERE e.event_name = 'purchase')
            SELECT COUNT(*) FILTER (WHERE is_internal), COUNT(*) FILTER (WHERE NOT is_internal)
            FROM o WHERE ISODOW(d) <= 5
            """).fetchone()
        ev["qa_weekday_order_pct"] = _entry(
            100 * qa / organic, "QA orders per 100 real orders on business weekdays",
            ["deduplicated on order_id", "business time zone"])
        n_ref, = con.execute("SELECT COUNT(*) FROM refunds").fetchone()
        ev["n_refunds"] = _entry(n_ref, "rows in refunds", ["count"])
        ev.update(_run_evidence(con, key))
    finally:
        con.close()
    return ev


RUN_CHECKS = ["every logged query re-executed against a fresh build (cli.py validate)",
              "graded against answer_key.json"]


def _run_evidence(con, key: dict[str, dict]) -> dict[str, dict]:
    """Evidence derived from the saved Copilot-agent run, if there is one."""
    import statistics

    from analyst_eval.gold import create_gold_views
    from analyst_eval.grading import grade_answer
    from analyst_eval.questions import QUESTIONS_BY_ID, TOLERANCE
    from analyst_eval.runs import list_runs, load_run

    runs = [p for p in list_runs() if load_run(p)[0].get("runner_kind") == "copilot-agent"]
    if not runs:
        return {}
    _, answers, _ = load_run(runs[-1])

    create_gold_views(con, Fixes().without("timezone"))
    utc_gold = {}
    for q in QUESTIONS_BY_ID.values():
        if q.gold_sql:
            row = con.execute(q.gold_sql).fetchone()
            utc_gold[q.id] = None if row[0] is None else float(row[0])

    ev: dict[str, dict] = {}
    for cond in sorted({a["condition"] for a in answers}):
        xs = [a for a in answers if a["condition"] == cond]
        grades = [grade_answer(a, key[a["question_id"]]) for a in xs]
        wrong = [(a, g) for a, g in zip(xs, grades, strict=True) if not g.correct]
        n = len(xs)

        def tz_only(a) -> bool:
            q = QUESTIONS_BY_ID[a["question_id"]]
            alt = utc_gold.get(q.id)
            return (a["value"] is not None and alt is not None
                    and abs(alt - a["value"]) <= TOLERANCE.get(q.unit or "", 0))

        p = f"run.{cond}."
        ev[p + "n"] = _entry(n, f"answers in {cond}", RUN_CHECKS)
        ev[p + "correct"] = _entry(sum(g.correct for g in grades), "correct answers", RUN_CHECKS)
        ev[p + "accuracy_pct"] = _entry(100 * sum(g.correct for g in grades) / n,
                                        "percent correct", RUN_CHECKS)
        ev[p + "material_pct"] = _entry(100 * sum(g.material_ok for g in grades) / n,
                                        "percent within 1% of gold", RUN_CHECKS)
        ev[p + "wrong"] = _entry(len(wrong), "answers not correct", RUN_CHECKS)
        ev[p + "material_wrong"] = _entry(sum(not g.material_ok for _, g in wrong),
                                          "answers more than 1% from gold", RUN_CHECKS)
        ev[p + "confidently_wrong"] = _entry(
            sum(g.outcome == "confidently_wrong" for g in grades),
            "wrong with status answered", RUN_CHECKS)
        ev[p + "caveated_wrong"] = _entry(sum(g.outcome == "caveated_wrong" for g in grades),
                                          "wrong with status answered_with_caveat", RUN_CHECKS)
        ev[p + "matched_naive"] = _entry(sum(g.fell_for_naive for g in grades),
                                         "wrong answers equal to the naive query's", RUN_CHECKS)
        ev[p + "wrong_tz_only"] = _entry(
            sum(tz_only(a) for a, _ in wrong),
            "wrong answers equal to gold computed in UTC instead of Pacific time",
            RUN_CHECKS + ["gold recomputed with only the timezone rule switched off"])
        ev[p + "sql_per_q"] = _entry(statistics.mean(a["sql_calls"] for a in xs),
                                     "mean logged queries per question", RUN_CHECKS)
        ev[p + "median_seconds"] = _entry(
            statistics.median(a["extra"]["wall_seconds"] for a in xs),
            "median seconds from first to last tool call", RUN_CHECKS)
        rc = [a["reconcile"] for a in xs if a.get("reconcile")]
        if rc:
            ev[p + "reconciled"] = _entry(len(rc), "answers that went through reconcile",
                                          RUN_CHECKS)
            ev[p + "reconcile_match"] = _entry(sum(r["match"] is True for r in rc),
                                               "reconciles where routes matched", RUN_CHECKS)
            ev[p + "reconcile_changed"] = _entry(sum(bool(r["changed"]) for r in rc),
                                                 "reconciles that changed the answer",
                                                 RUN_CHECKS)
    return ev


def write_evidence(ev: dict, path: Path = EVIDENCE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ev, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_evidence(path: Path = EVIDENCE_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
