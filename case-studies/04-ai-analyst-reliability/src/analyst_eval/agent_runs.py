"""Copilot-agent runs: blind bundles, log import, and replay validation.

The API harness (``agent.py``) drives a model over HTTP. This module supports the other
way to run the same experiment: an agent (here, a GitHub Copilot sub-agent) works in a
*blind bundle* -- a folder outside the repo holding only the raw database, one
condition's context, the protocol and ``tool.py``. No answer key, gold SQL or grading code
is in the bundle. ``tool.py`` logs every query, result and answer; this module turns those
logs into run records that the normal grading and reporting code consumes, and validates
them by re-executing every logged query against a fresh warehouse build.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from analyst_eval import DB_PATH
from analyst_eval import bundle_tool as tool
from analyst_eval.answer_key import ANSWER_KEY_PATH
from analyst_eval.conditions import CONDITIONS, context_parts, read_skill
from analyst_eval.questions import QUESTIONS_BY_ID, TOLERANCE, Question
from analyst_eval.runs import SCHEMA_VERSION, canonical_transcript, file_sha
from analyst_eval.sqlexec import execute, format_result, to_number
from analyst_eval.warehouse import DEFAULT_N_USERS, DEFAULT_SEED, connect_readonly

RUNNER_KIND = "copilot-agent"
MAX_SQL = 8
SQL_TIMEOUT = 30.0
_SRC = Path(__file__).resolve().parent

AGENT_PROTOCOL = """\
# Analyst task

You are a data analyst answering one business question from a DuckDB database (DuckDB
SQL dialect). Your question and its question id are in the message that sent you here.

## Rules

- You can only learn about the data through `tool.py` in this folder. Do not open, list,
  search or read any file or folder outside this folder, do not read the database file
  directly, and do not use the web. Inside this folder, read only this file and files you
  write yourself.
- Work in `work/<question id>/` (create it). Write each query to a `.sql` file there and
  your answer to a `.json` file there.
- Run every command from this folder with this exact Python:
  `{python}`

## Tool

- `<python> tool.py sql <question id> work/<question id>/q1.sql` runs one read-only query
  and prints up to 50 rows. You may run at most {max_sql} queries for your question.
- `<python> tool.py answer <question id> work/<question id>/answer.json` submits your
  answer. Read the tool's reply: if it asks for another step, do that step.
- You are done when the tool prints `FINAL ANSWER RECORDED`. Then reply with one line:
  your status and value.

## Answer format

The answer file must contain one JSON object:

```json
{{"status": "answered" | "answered_with_caveat" | "abstained",
 "value": <number, or null if abstained>,
 "unit": "count" | "usd" | "percent" | "ratio",
 "final_sql": "<the query that produces value>",
 "assumptions": ["..."],
 "checks": ["..."]}}
```
- "answered": you are confident the number answers the question as asked.
- "answered_with_caveat": you gave a number but a judgement call could change it.
- "abstained": the question cannot be answered reliably from this data.
Percents are 0-100. Money is US dollars. Give the exact value, not a rounded one.
"""


def agent_md(condition: str, python: str, max_sql: int = MAX_SQL) -> str:
    parts = [AGENT_PROTOCOL.format(python=python, max_sql=max_sql),
             *context_parts(CONDITIONS[condition])]
    return "\n\n".join(parts) + "\n"


def _lib_sources() -> list[Path]:
    return [_SRC / "sqlexec.py", _SRC / "reconcile.py", _SRC / "bundle_tool.py"]


def agent_prompt_hash(condition: str, max_sql: int = MAX_SQL) -> str:
    h = hashlib.sha256(agent_md(condition, "<python>", max_sql).encode("utf-8"))
    if CONDITIONS[condition].reconcile:
        h.update(read_skill("reconcile-results").encode("utf-8"))
    for p in _lib_sources():
        h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


def build_bundles(root: Path | str, conditions: list[str], questions: list[Question],
                  python: str, db_path: Path | str = DB_PATH) -> dict:
    """Write one blind folder per condition under ``root``."""
    root = Path(root)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "max_sql": MAX_SQL,
        "questions": [q.id for q in questions],
        "conditions": {c: agent_prompt_hash(c) for c in conditions},
        "db_sha": file_sha(Path(db_path)),
    }
    for c in conditions:
        d = root / c
        if d.exists():
            shutil.rmtree(d)
        lib = d / "_lib" / "analyst_eval"
        lib.mkdir(parents=True)
        (lib / "__init__.py").write_text("", encoding="utf-8")
        shutil.copy(_SRC / "sqlexec.py", lib / "sqlexec.py")
        shutil.copy(_SRC / "reconcile.py", lib / "reconcile.py")
        shutil.copy(_SRC / "bundle_tool.py", d / "tool.py")
        shutil.copy(db_path, d / "analyst.db")
        cfg = {
            "condition": c,
            "reconcile": CONDITIONS[c].reconcile,
            "max_sql": MAX_SQL,
            "sql_timeout": SQL_TIMEOUT,
            "tolerance": {q.id: TOLERANCE.get(q.unit or "", 1e-6) for q in questions},
            "reconcile_skill": read_skill("reconcile-results"),
        }
        (d / "tool_config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        (d / "AGENT.md").write_text(agent_md(c, python), encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def record_from_log(events: list[dict], qid: str, condition: str) -> dict:
    """Derive the graded answer fields from a tool log. Pure function of the log."""
    st = tool.log_state(events)
    final = next((e["answer"] for e in events
                  if e["type"] == "answer" and e["phase"] == "final"), None)
    rec = {
        "question_id": qid, "condition": condition, "trial": 0,
        "status": "no_answer", "value": None, "unit": None, "final_sql": None,
        "assumptions": [], "checks": [], "transcript": events,
        "input_tokens": 0, "output_tokens": 0, "model_calls": None,
        "sql_calls": st["sql_calls"],
        "format_errors": sum(e["type"] == "rejected" for e in events),
        "value_matches_final_sql": None, "reconcile": None, "error": None,
        "extra": {"wall_seconds": round(events[-1]["ts"] - events[0]["ts"], 3)
                  if events else 0.0},
    }
    if final is not None:
        rec.update(
            status=final["status"], value=to_number(final.get("value")),
            unit=final.get("unit"), final_sql=final.get("final_sql") or None,
            assumptions=[str(x) for x in final.get("assumptions") or []],
            checks=[str(x) for x in final.get("checks") or []],
        )
    if st["initial"] is not None:
        rc = next((e for e in events if e["type"] == "reconcile"), None)
        initial = st["initial"]
        rec["reconcile"] = {
            "primary_sql": initial.get("final_sql"),
            "initial_value": to_number(initial.get("value")),
            "initial_status": initial.get("status"),
            "independent_sql": rc["sql"] if rc else None,
            "match": rc["match"] if rc else None,
            "diff": rc["diff"] if rc else None,
            "final_value": rec["value"], "final_status": rec["status"],
            "changed": rec["value"] != to_number(initial.get("value"))
            or rec["status"] != initial.get("status"),
        }
    return rec


def _value_matches(con, rec: dict) -> bool | None:
    if rec["status"] in ("abstained", "no_answer") or rec["value"] is None or not rec["final_sql"]:
        return None
    own = execute(con, rec["final_sql"], SQL_TIMEOUT).scalar()
    tol = TOLERANCE.get(QUESTIONS_BY_ID[rec["question_id"]].unit or "", 1e-6)
    return own is not None and abs(own - rec["value"]) <= tol


def _read_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def import_bundles(root: Path | str, model: str, out_path: Path,
                   db_path: Path | str = DB_PATH, questions: list[str] | None = None) -> Path:
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    qids = questions or manifest["questions"]
    unknown = sorted(set(qids) - set(manifest["questions"]))
    if unknown:
        raise SystemExit(f"Questions {unknown} are not in this bundle.")
    for c, h in manifest["conditions"].items():
        if agent_prompt_hash(c, manifest["max_sql"]) != h:
            raise SystemExit(f"Bundle for {c} was built from different prompts or tool code.")
    con = connect_readonly(db_path)
    answers = []
    try:
        for c in manifest["conditions"]:
            for qid in qids:
                rec = record_from_log(_read_log(root / c / "logs" / f"{qid}.jsonl"), qid, c)
                rec["value_matches_final_sql"] = _value_matches(con, rec)
                answers.append(rec)
    finally:
        con.close()
    meta = {
        "type": "meta", "schema_version": SCHEMA_VERSION, "runner_kind": RUNNER_KIND,
        "run_id": f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_github-copilot_{model}",
        "provider": "github-copilot", "model": model, "temperature": None,
        "started_at": manifest["created_at"],
        "conditions": manifest["conditions"],
        "answer_key_sha": file_sha(ANSWER_KEY_PATH),
        "agent_config": {"max_sql": manifest["max_sql"], "sql_timeout": SQL_TIMEOUT},
        "trials": 1, "pricing": None,
        "dataset": {"n_users": DEFAULT_N_USERS, "seed": DEFAULT_SEED},
        "db_sha": manifest["db_sha"],
    }
    end = {"type": "end", "finished_at": datetime.now(timezone.utc).isoformat(),
           "input_tokens": 0, "output_tokens": 0, "stopped": None}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(meta) + "\n")
        for a in answers:
            fh.write(json.dumps({"type": "answer", **a}, default=str) + "\n")
        fh.write(json.dumps(end) + "\n")
    return out_path


def validate_agent_answer(rec: dict, db_path: Path | str) -> list[str]:
    """Re-execute every logged query and diff; rebuild the record from its log."""
    problems = []
    events = rec["transcript"]
    tol = TOLERANCE.get(QUESTIONS_BY_ID[rec["question_id"]].unit or "", 1e-6)
    con = connect_readonly(db_path)
    try:
        initial_sql = None
        for i, e in enumerate(events):
            if e["type"] == "sql":
                fresh = format_result(execute(con, e["sql"], SQL_TIMEOUT))
            elif e["type"] == "reconcile":
                if initial_sql is None:
                    problems.append(f"event {i}: reconcile without an initial answer")
                    continue
                fresh, details, match = tool.reconcile_report(con, initial_sql, e["sql"], tol,
                                                              SQL_TIMEOUT)
                if match != e["match"]:
                    problems.append(f"event {i}: reconcile match differs on replay")
            else:
                if e["type"] == "answer" and e["phase"] == "initial":
                    initial_sql = e["answer"].get("final_sql")
                continue
            if canonical_transcript([{"role": "tool", "content": fresh}]) != \
                    canonical_transcript([{"role": "tool", "content": e["output"]}]):
                problems.append(f"event {i}: {e['type']} output differs on replay")
        rebuilt = record_from_log(events, rec["question_id"], rec["condition"])
        rebuilt["value_matches_final_sql"] = _value_matches(con, rebuilt)
    finally:
        con.close()
    for k, v in rebuilt.items():
        if k in ("transcript", "trial"):
            continue
        if json.loads(json.dumps(v, default=str)) != rec.get(k):
            problems.append(f"field {k!r} differs from its log")
    return problems
