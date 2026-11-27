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
    finally:
        con.close()
    return ev


def write_evidence(ev: dict, path: Path = EVIDENCE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ev, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_evidence(path: Path = EVIDENCE_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
