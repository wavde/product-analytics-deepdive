"""Evidence for the case README: every number in the memo's cited sections comes from here.

Built deterministically from the warehouse and the answer key -- no model output. Each
entry records the value, how it was computed, and which checks it passed, following the
cited-memo skill.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import duckdb

from analyst_eval import DB_PATH, HOLDOUT_DB_PATH, RESULTS_DIR
from analyst_eval.answer_key import ANSWER_KEY_PATH, HOLDOUT_KEY_PATH, load_answer_key, variant_of
from analyst_eval.gold import Fixes, create_gold_views
from analyst_eval.grading import grade_answer
from analyst_eval.questions import QUESTIONS_BY_ID, TOLERANCE
from analyst_eval.runs import list_runs, load_run

EVIDENCE_PATH = RESULTS_DIR / "evidence.json"
# The cleaning rules the context pack documents. resubmitted_orders is deliberately left
# out: it only matters on the holdout warehouse, whose trap the context pack never mentions.
CLEANING_RULES = ("duplicates", "internal_accounts", "system_events", "timezone")
KEY_CHECKS = [
    "gold computed through views implementing every ground rule in definitions.md",
    "answer key regenerated from a fresh warehouse build and compared in CI",
]


def _entry(value: float, how: str, checks: list[str]) -> dict:
    return {"value": round(float(value), 4), "how": how, "checks": checks}


def build_evidence(db_path: Path | str = DB_PATH, key_path: Path = ANSWER_KEY_PATH,
                   holdout_db_path: Path | str | None = HOLDOUT_DB_PATH) -> dict:
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

    for t in sorted(CLEANING_RULES) + ["refunds", "partial_period", "units", "definition",
                                       "not_instrumented"]:
        ev[f"live_{t}"] = _entry(
            sum(t in r["traps"] for r in key.values()),
            f"questions tagged {t}"
            + (" (measured by disabling only this rule)" if t in CLEANING_RULES else ""),
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
    if holdout_db_path is not None and Path(holdout_db_path).exists() and HOLDOUT_KEY_PATH.exists():
        ev.update(_holdout_evidence(holdout_db_path, load_answer_key(HOLDOUT_KEY_PATH)))
    return ev


RUN_CHECKS = ["every logged query re-executed against a fresh build (cli.py validate)",
              "graded against answer_key.json"]


def _alt_gold(con, rules: tuple[str, ...], qids) -> dict[frozenset[str], dict[str, float | None]]:
    """Gold recomputed with every non-empty combination of ``rules`` switched off, so a wrong
    answer can be attributed to data cleaning (some combination matches) or not."""
    alt: dict[frozenset[str], dict[str, float | None]] = {}
    for r in range(1, len(rules) + 1):
        for off in combinations(rules, r):
            fixes = Fixes()
            for name in off:
                fixes = fixes.without(name)
            create_gold_views(con, fixes)
            vals: dict[str, float | None] = {}
            for qid in qids:
                q = QUESTIONS_BY_ID[qid]
                if q.gold_sql:
                    row = con.execute(q.gold_sql).fetchone()
                    vals[q.id] = None if row[0] is None else float(row[0])
            alt[frozenset(off)] = vals
    create_gold_views(con)
    return alt


def _agent_answers(variant: str) -> dict[str, list[dict]]:
    by_model: dict[str, list[dict]] = defaultdict(list)
    for p in list_runs():
        meta, answers, _ = load_run(p)
        if meta.get("runner_kind") == "copilot-agent" and variant_of(meta) == variant:
            by_model[meta["model"]] += answers
    return by_model


def _run_evidence(con, key: dict[str, dict]) -> dict[str, dict]:
    """Evidence from saved Copilot-agent runs, keyed run.<model>.t<trial>.<condition>.*"""
    by_model = _agent_answers("main")
    if not by_model:
        return {}
    alt_gold = _alt_gold(con, CLEANING_RULES, list(key))

    ev: dict[str, dict] = {}
    for model, all_answers in by_model.items():
        for cond in sorted({a["condition"] for a in all_answers}):
            xs = [a for a in all_answers if a["condition"] == cond]
            trials = {a.get("trial", 0) for a in xs}
            if len(trials) < 2:
                continue
            outcomes: dict[str, set] = defaultdict(set)
            seen: dict[str, set] = defaultdict(set)
            for a in xs:
                outcomes[a["question_id"]].add(grade_answer(a, key[a["question_id"]]).outcome)
                seen[a["question_id"]].add(a.get("trial", 0))
            full = [q for q in seen if seen[q] == trials]
            ev[f"run.{model}.{cond}.same_outcome"] = _entry(
                sum(len(outcomes[q]) == 1 for q in full),
                f"questions with the same graded outcome in all {len(trials)} trials",
                RUN_CHECKS)
            ev[f"run.{model}.{cond}.n_repeated"] = _entry(
                len(full), "questions run in every trial", RUN_CHECKS)
        for trial in sorted({a.get("trial", 0) for a in all_answers}):
            answers = [a for a in all_answers if a.get("trial", 0) == trial]
            ev.update(_condition_evidence(f"run.{model}.t{trial}.", answers, key, alt_gold))
    return ev


def _matching_rule_sets(a: dict, alt_gold: dict[frozenset[str], dict[str, float | None]]
                        ) -> list[frozenset[str]]:
    """Combinations of switched-off cleaning rules whose gold equals this answer."""
    q = QUESTIONS_BY_ID[a["question_id"]]
    if a["value"] is None:
        return []
    tol = TOLERANCE.get(q.unit or "", 0)
    return [off for off, vals in alt_gold.items()
            if vals.get(q.id) is not None and abs(vals[q.id] - a["value"]) <= tol]


def _condition_evidence(prefix: str, answers: list[dict], key: dict[str, dict],
                        alt_gold: dict[frozenset[str], dict[str, float | None]]
                        ) -> dict[str, dict]:
    ev: dict[str, dict] = {}
    rules = sorted(set().union(*alt_gold)) if alt_gold else []
    combos = f"gold recomputed under all {len(alt_gold)} combinations of switched-off rules"
    for cond in sorted({a["condition"] for a in answers}):
        xs = [a for a in answers if a["condition"] == cond]
        grades = [grade_answer(a, key[a["question_id"]]) for a in xs]
        wrong = [(a, g) for a, g in zip(xs, grades, strict=True) if not g.correct]
        n = len(xs)
        matches = [_matching_rule_sets(a, alt_gold) for a, _ in wrong]
        tz_only = sum(frozenset({"timezone"}) in ms for ms in matches)
        kept_internal = sum(bool(ms) and all("internal_accounts" in m for m in ms)
                            for ms in matches)

        p = f"{prefix}{cond}."
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
            tz_only,
            "wrong answers equal to gold computed in UTC instead of Pacific time",
            RUN_CHECKS + ["gold recomputed with only the timezone rule switched off"])
        ev[p + "wrong_cleaning"] = _entry(
            sum(bool(ms) for ms in matches),
            "wrong answers equal to gold with some combination of the data-cleaning rules ("
            + ", ".join(rules) + ") switched off",
            RUN_CHECKS + [combos])
        ev[p + "wrong_kept_internal"] = _entry(
            kept_internal,
            "wrong answers explained only by combinations that keep internal accounts in",
            RUN_CHECKS + [combos])
        if "resubmitted_orders" in rules:
            ev[p + "wrong_resubmit_only"] = _entry(
                sum(frozenset({"resubmitted_orders"}) in ms for ms in matches),
                "wrong answers equal to gold with only the re-submitted-orders rule "
                "switched off (every documented rule applied, re-submissions counted)",
                RUN_CHECKS + [combos])
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


HOLDOUT_CHECKS = ["holdout gold computed through the same views with one extra rule "
                  "(one order per order_id, first submission kept)",
                  "holdout answer key regenerated from a fresh build and compared in CI"]


def _holdout_evidence(db_path: Path | str, key: dict[str, dict]) -> dict[str, dict]:
    """Facts about the holdout warehouse, plus runs against it (run.<model>.holdout.t<n>.*)."""
    ev: dict[str, dict] = {}
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        con.execute("SET TimeZone = 'UTC'")
        events, orders = con.execute(
            "SELECT COUNT(DISTINCT event_id), COUNT(DISTINCT order_id) FROM events "
            "WHERE event_name = 'purchase'").fetchone()
        ev["holdout.resubmitted_events"] = _entry(
            events - orders, "purchase event_ids beyond one per order_id",
            ["COUNT(DISTINCT event_id) vs COUNT(DISTINCT order_id) on purchase rows"])
        ev["holdout.n_questions"] = _entry(len(key), "rows in answer_key_holdout.json",
                                           ["count"])
        ev["holdout.live_resubmitted_orders"] = _entry(
            sum("resubmitted_orders" in r["traps"] for r in key.values()),
            "holdout questions whose gold moves when only the re-submitted-orders rule is off",
            HOLDOUT_CHECKS)
        alt_gold = _alt_gold(con, (*CLEANING_RULES, "resubmitted_orders"), list(key))
        no_resub = alt_gold[frozenset({"resubmitted_orders"})]
        for qid, r in key.items():
            if r["gold"] is None or no_resub.get(qid) is None:
                continue
            ev[f"holdout.{qid}.gold"] = _entry(r["gold"], f"holdout gold for {qid}",
                                               HOLDOUT_CHECKS)
            ev[f"holdout.{qid}.event_dedup"] = _entry(
                no_resub[qid], f"{qid} with every documented rule but re-submissions counted",
                HOLDOUT_CHECKS)
            if r["gold"]:
                ev[f"holdout.{qid}.event_dedup_error_pct"] = _entry(
                    100 * (no_resub[qid] - r["gold"]) / r["gold"],
                    f"(event_dedup - gold) / gold for {qid}", HOLDOUT_CHECKS)
        for model, all_answers in _agent_answers("holdout").items():
            for trial in sorted({a.get("trial", 0) for a in all_answers}):
                answers = [a for a in all_answers if a.get("trial", 0) == trial]
                ev.update(_condition_evidence(f"run.{model}.holdout.t{trial}.", answers, key,
                                              alt_gold))
    finally:
        con.close()
    return ev


def write_evidence(ev: dict, path: Path = EVIDENCE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ev, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_evidence(path: Path = EVIDENCE_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
