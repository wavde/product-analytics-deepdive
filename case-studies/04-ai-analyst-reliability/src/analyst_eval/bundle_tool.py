"""Analyst tool for Copilot-agent runs. Copied into each blind bundle as ``tool.py``.

The agent's only interface to the data. Every command and its output is appended to
``logs/<question id>.jsonl`` by this tool, so the record of what happened does not depend
on the agent's own report. It enforces the same protocol as the API harness
(``analyst_eval.agent``): a query budget, a JSON answer contract, and in the reconcile
condition a mandatory independent recomputation and data-diff before the final answer.

Usage (from the bundle folder):
    python tool.py sql       <question id> <file.sql>
    python tool.py answer    <question id> <answer.json>
    python tool.py reconcile <question id> <file.sql>
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "_lib"))

from analyst_eval.reconcile import diff_results  # noqa: E402
from analyst_eval.sqlexec import execute, format_result, to_number  # noqa: E402

VALID_STATUS = ("answered", "answered_with_caveat", "abstained")
FINAL = "FINAL ANSWER RECORDED"
RECONCILE_STEP = """\
RECONCILE STEP. Before your answer is accepted, follow the reconcile-results skill below.
Write an independent query for the same metric that takes a different route from your
final_sql. It must return the metric in the same shape as your final_sql (same number of
columns, value columns in the same positions). Submit it with:
    tool.py reconcile <question id> <file.sql>

{skill}
"""
RECONCILE_FOLLOWUP = """\
Data-diff of your final_sql (primary) against the independent query:
{report}

Now submit your final answer with `tool.py answer`. You may run more queries first if you
need to resolve a mismatch. If the routes disagree and you cannot explain why, use
"answered_with_caveat" or "abstained".
"""
_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.S | re.I)


def connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(db_path), read_only=True)
    con.execute("SET TimeZone = 'UTC'")
    con.execute("SET threads = 1")
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con


def parse_answer(text: str) -> tuple[dict | None, str | None]:
    m = _FENCE.search(text)
    raw = (m.group(1) if m else text).strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as err:
        return None, f"answer file is not valid JSON ({err.msg})"
    if not isinstance(obj, dict):
        return None, "answer must be a JSON object"
    if obj.get("status") not in VALID_STATUS:
        return None, f"status must be one of {list(VALID_STATUS)}"
    return obj, None


def reconcilable(ans: dict) -> bool:
    return (ans.get("status") != "abstained" and to_number(ans.get("value")) is not None
            and bool(ans.get("final_sql")))


def log_state(events: list[dict]) -> dict:
    answers = [e for e in events if e["type"] == "answer"]
    return {
        "sql_calls": sum(e["type"] == "sql" for e in events),
        "final": any(e["phase"] == "final" for e in answers),
        "initial": next((e["answer"] for e in answers if e["phase"] == "initial"), None),
        "reconciled": any(e["type"] == "reconcile" for e in events),
    }


def reconcile_report(con, primary_sql: str, independent_sql: str, tol: float,
                     timeout: float) -> tuple[str, dict, bool]:
    primary = execute(con, primary_sql, timeout)
    independent = execute(con, independent_sql, timeout)
    rep = diff_results(primary, independent, tol)
    body = (f"{rep.summary}\n\nPrimary result:\n{format_result(primary)}\n\n"
            f"Independent result:\n{format_result(independent)}")
    return RECONCILE_FOLLOWUP.format(report=body), rep.details, rep.match


def run(argv: list[str], here: Path = HERE) -> str:
    here = here.resolve()
    cfg = json.loads((here / "tool_config.json").read_text(encoding="utf-8"))
    if len(argv) != 3 or argv[0] not in ("sql", "answer", "reconcile"):
        return "Usage: tool.py sql|answer|reconcile <question id> <file>"
    cmd, qid, file_arg = argv
    if qid not in cfg["tolerance"]:
        return f"Unknown question id {qid!r}."
    path = (here / file_arg).resolve()
    if here not in path.parents or not path.is_file():
        return "The file must exist inside this folder (e.g. work/<question id>/q1.sql)."
    text = path.read_text(encoding="utf-8-sig")

    log = here / "logs" / f"{qid}.jsonl"
    log.parent.mkdir(exist_ok=True)
    events = ([json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x]
              if log.exists() else [])

    def record(event: dict, output: str) -> str:
        event["ts"] = round(time.time(), 3)
        event["output"] = output
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
        return output

    st = log_state(events)
    if st["final"]:
        return f"This question already has a final answer. {FINAL}"
    awaiting = st["initial"] is not None and not st["reconciled"]
    con = connect(here / "analyst.db")
    try:
        if cmd == "sql":
            if awaiting:
                return record({"type": "rejected", "command": cmd, "text": text},
                              "A reconcile step is pending. Submit your independent query with "
                              "`tool.py reconcile` first.")
            if st["sql_calls"] >= cfg["max_sql"]:
                return record({"type": "rejected", "command": cmd, "text": text},
                              "Query budget exhausted. Submit your final answer with "
                              "`tool.py answer`.")
            out = format_result(execute(con, text, cfg["sql_timeout"]))
            return record({"type": "sql", "sql": text}, out)

        if cmd == "reconcile":
            if not awaiting:
                return record({"type": "rejected", "command": cmd, "text": text},
                              "No reconcile step is pending for this question.")
            out, details, match = reconcile_report(
                con, st["initial"]["final_sql"], text, cfg["tolerance"][qid], cfg["sql_timeout"])
            return record({"type": "reconcile", "sql": text, "match": match, "diff": details}, out)

        ans, err = parse_answer(text)
        if ans is None:
            return record({"type": "rejected", "command": cmd, "text": text},
                          f"Answer rejected: {err}. Fix the file and submit again.")
        if awaiting:
            return record({"type": "rejected", "command": cmd, "text": text},
                          "A reconcile step is pending. Submit your independent query with "
                          "`tool.py reconcile` first.")
        if cfg["reconcile"] and st["initial"] is None and reconcilable(ans):
            return record({"type": "answer", "phase": "initial", "answer": ans},
                          RECONCILE_STEP.format(skill=cfg["reconcile_skill"]))
        return record({"type": "answer", "phase": "final", "answer": ans}, FINAL)
    finally:
        con.close()


if __name__ == "__main__":
    print(run(sys.argv[1:]))
