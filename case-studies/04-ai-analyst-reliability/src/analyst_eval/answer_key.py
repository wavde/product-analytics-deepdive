"""Compute the answer key: gold answer, naive answer and live traps for every question.

A data-cleaning trap is "live" for a question when switching off just that rule in the
gold views moves the answer outside the question's grading tolerance.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from analyst_eval import DB_PATH, HOLDOUT_DB_PATH, QUESTIONS_DIR
from analyst_eval.gold import Fixes, create_gold_views
from analyst_eval.questions import HOLDOUT_QUESTIONS, QUESTIONS, Question

ANSWER_KEY_PATH = QUESTIONS_DIR / "answer_key.json"
HOLDOUT_KEY_PATH = QUESTIONS_DIR / "answer_key_holdout.json"

# A "variant" is a warehouse plus its answer key. "main" is the warehouse the context pack
# documents; "holdout" adds one trap the context pack doesn't mention.
VARIANTS = {
    "main": {"db": DB_PATH, "key": ANSWER_KEY_PATH, "questions": QUESTIONS},
    "holdout": {"db": HOLDOUT_DB_PATH, "key": HOLDOUT_KEY_PATH,
                "questions": HOLDOUT_QUESTIONS},
}


def variant_of(meta: dict) -> str:
    return meta.get("variant", "main")


def _scalar(con: duckdb.DuckDBPyConnection, sql: str) -> float | None:
    row = con.execute(sql).fetchone()
    if row is None or row[0] is None:
        return None
    return round(float(row[0]), 4)


def _differs(a: float | None, b: float | None, tol: float) -> bool:
    if a is None or b is None:
        return a is not b
    return abs(a - b) > tol


def compute_answer_key(
    db_path: Path | str = DB_PATH, questions: list[Question] = QUESTIONS
) -> list[dict]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        con.execute("SET TimeZone = 'UTC'")
        gold: dict[str, float | None] = {}
        create_gold_views(con, Fixes())
        for q in questions:
            gold[q.id] = _scalar(con, q.gold_sql) if q.gold_sql else None

        live: dict[str, list[str]] = {q.id: [] for q in questions}
        for name in Fixes.names():
            create_gold_views(con, Fixes().without(name))
            for q in questions:
                if q.gold_sql and _differs(_scalar(con, q.gold_sql), gold[q.id], q.tolerance):
                    live[q.id].append(name)

        key = []
        for q in questions:
            naive = _scalar(con, q.naive_sql) if q.naive_sql else None
            key.append(
                {
                    "id": q.id,
                    "category": q.category,
                    "question": q.question,
                    "unit": q.unit,
                    "expect_abstain": q.expect_abstain,
                    "gold": gold[q.id],
                    "naive": naive,
                    "naive_is_wrong": (
                        q.expect_abstain
                        or (naive is not None and _differs(naive, gold[q.id], q.tolerance))
                    )
                    if q.naive_sql
                    else None,
                    "traps": sorted(set(q.traps) | set(live[q.id])),
                }
            )
        return key
    finally:
        con.close()


def write_answer_key(key: list[dict], path: Path = ANSWER_KEY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")


def load_answer_key(path: Path = ANSWER_KEY_PATH) -> dict[str, dict]:
    return {row["id"]: row for row in json.loads(path.read_text(encoding="utf-8"))}
