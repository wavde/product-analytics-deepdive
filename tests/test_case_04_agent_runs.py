"""Case 04: Copilot-agent runs -- blind bundles, the analyst tool, log import and validation.

Tool commands here are scripted to test the plumbing; they are not model results.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

import pytest
from analyst_eval.agent_runs import build_bundles, import_bundles
from analyst_eval.answer_key import load_answer_key
from analyst_eval.bundle_tool import FINAL, run
from analyst_eval.grading import grade_answer
from analyst_eval.questions import QUESTIONS, QUESTIONS_BY_ID
from analyst_eval.runs import load_run, validate_run

KEY = load_answer_key()
T01_INDEPENDENT = """
SELECT COUNT(DISTINCT e.order_id)
FROM events e JOIN users u USING (user_id)
WHERE NOT u.is_internal AND e.event_name = 'purchase'
  AND CAST(e.event_ts AT TIME ZONE 'UTC' AT TIME ZONE 'America/Los_Angeles' AS DATE)
      BETWEEN DATE '2025-02-01' AND DATE '2025-02-28'
"""


@pytest.fixture()
def bundles(analyst_db, tmp_path):
    qs = [QUESTIONS_BY_ID[i] for i in ("c01", "t01", "u02")]
    build_bundles(tmp_path, ["no_context", "full_context_reconcile"], qs, sys.executable,
                  analyst_db)
    return tmp_path


def _call(folder, cmd, qid, name, body) -> str:
    work = folder / "work" / qid
    work.mkdir(parents=True, exist_ok=True)
    (work / name).write_text(body if isinstance(body, str) else json.dumps(body),
                             encoding="utf-8")
    return run([cmd, qid, f"work/{qid}/{name}"], here=folder)


def _answer(sql_attr: str, qid: str, value_attr: str = "gold") -> dict:
    q = QUESTIONS_BY_ID[qid]
    return {"status": "answered", "value": KEY[qid][value_attr], "unit": q.unit,
            "final_sql": getattr(q, sql_attr)}


def test_bundle_is_blind(bundles):
    files = [p for p in bundles.rglob("*") if p.is_file() and p.suffix != ".db"]
    text = "\n".join(p.read_text(encoding="utf-8") for p in files)
    for q in QUESTIONS:
        assert q.question not in text, q.id
        if q.gold_sql:
            assert q.gold_sql not in text, q.id
    assert "g_orders" not in text and "answer_key" not in text and "naive" not in text
    no_ctx = (bundles / "no_context" / "AGENT.md").read_text(encoding="utf-8")
    full = (bundles / "full_context_reconcile" / "AGENT.md").read_text(encoding="utf-8")
    assert "Metric definitions" not in no_ctx and "Metric definitions" in full


def test_copied_tool_runs_standalone(bundles):
    folder = bundles / "no_context"
    (folder / "work").mkdir()
    (folder / "work" / "q.sql").write_text("SELECT COUNT(*) FROM users", encoding="utf-8")
    out = subprocess.run([sys.executable, "tool.py", "sql", "c01", "work/q.sql"], cwd=folder,
                         capture_output=True, text=True, check=True).stdout
    assert "5010" in out


def test_tool_enforces_protocol(bundles):
    folder = bundles / "full_context_reconcile"
    assert "inside this folder" in run(["sql", "c01", "../no_context/tool.py"], here=folder)
    assert "rejected" in _call(folder, "answer", "c01", "a.json", "{not json")
    out = _call(folder, "answer", "t01", "a.json", _answer("naive_sql", "t01", "naive"))
    assert out.startswith("RECONCILE STEP")
    assert "reconcile step is pending" in _call(folder, "sql", "t01", "q.sql", "SELECT 1")
    assert "MISMATCH" in _call(folder, "reconcile", "t01", "r.sql", T01_INDEPENDENT)
    final = {**_answer("naive_sql", "t01"), "final_sql": T01_INDEPENDENT}
    assert _call(folder, "answer", "t01", "b.json", final) == FINAL
    assert "already has a final answer" in _call(folder, "sql", "t01", "q.sql", "SELECT 1")
    for i in range(8):
        _call(folder, "sql", "c01", f"q{i}.sql", "SELECT 1")
    assert "budget exhausted" in _call(folder, "sql", "c01", "q9.sql", "SELECT 1")


def _script_agents(bundles):
    nc, rc = bundles / "no_context", bundles / "full_context_reconcile"
    for folder in (nc, rc):
        _call(folder, "sql", "c01", "q.sql", QUESTIONS_BY_ID["c01"].naive_sql)
        _call(folder, "answer", "c01", "a.json", _answer("naive_sql", "c01"))
        _call(folder, "answer", "u02", "a.json", {"status": "abstained", "value": None})
        _call(folder, "sql", "t01", "q.sql", "SELECT event_name, COUNT(*) FROM events GROUP BY 1")
        _call(folder, "answer", "t01", "a.json", _answer("naive_sql", "t01", "naive"))
    _call(rc, "reconcile", "t01", "r.sql", T01_INDEPENDENT)
    _call(rc, "answer", "t01", "b.json", {**_answer("naive_sql", "t01"),
                                          "final_sql": T01_INDEPENDENT})


def test_import_validate_and_grade(bundles, analyst_db, tmp_path):
    _script_agents(bundles)
    out = import_bundles(bundles, "scripted", tmp_path / "run.jsonl", analyst_db)
    assert validate_run(out, analyst_db) == []
    meta, answers, _ = load_run(out)
    assert meta["runner_kind"] == "copilot-agent" and len(answers) == 6
    by = {(a["condition"], a["question_id"]): a for a in answers}
    grade = {k: grade_answer(a, KEY[a["question_id"]]).outcome for k, a in by.items()}
    assert grade[("no_context", "t01")] == "confidently_wrong"
    assert grade[("full_context_reconcile", "t01")] == "correct"
    assert grade[("no_context", "u02")] == "correct"
    rc = by[("full_context_reconcile", "t01")]["reconcile"]
    assert rc["match"] is False and rc["changed"] is True
    assert by[("full_context_reconcile", "t01")]["value_matches_final_sql"] is True


@pytest.mark.parametrize("tamper", ["sql_output", "value", "drop_event"])
def test_validation_catches_tampering(bundles, analyst_db, tmp_path, tamper):
    _script_agents(bundles)
    out = import_bundles(bundles, "scripted", tmp_path / "run.jsonl", analyst_db)
    lines = out.read_text(encoding="utf-8").splitlines()
    i = next(n for n, ln in enumerate(lines)
             if '"no_context"' in ln and '"question_id": "t01"' in ln)
    rec = json.loads(lines[i])
    if tamper == "sql_output":
        ev = next(e for e in rec["transcript"] if e["type"] == "sql")
        ev["output"] = ev["output"].replace("purchase", "purchases")
    elif tamper == "value":
        rec["value"] = KEY["t01"]["gold"]
    else:
        rec["transcript"] = [e for e in rec["transcript"] if e["type"] != "sql"]
    lines[i] = json.dumps(rec)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert validate_run(out, analyst_db)


def test_volatile_output_is_not_compared_but_other_edits_still_are(bundles, analyst_db, tmp_path):
    folder = bundles / "no_context"
    _call(folder, "sql", "c01", "v.sql", "SELECT current_date AS d, COUNT(*) AS n FROM users")
    _call(folder, "sql", "c01", "q.sql", QUESTIONS_BY_ID["c01"].naive_sql)
    _call(folder, "answer", "c01", "a.json", _answer("naive_sql", "c01"))
    out = import_bundles(bundles, "scripted", tmp_path / "run.jsonl", analyst_db,
                         questions=["c01"])
    lines = out.read_text(encoding="utf-8").splitlines()
    i = next(n for n, ln in enumerate(lines) if '"no_context"' in ln and '"c01"' in ln)
    rec = json.loads(lines[i])
    vol, plain = (e for e in rec["transcript"] if e["type"] == "sql")
    vol["output"] = re.sub(r"\d{4}-\d{2}-\d{2}", "1999-01-01", vol["output"])
    lines[i] = json.dumps(rec)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert validate_run(out, analyst_db) == []

    plain["output"] = plain["output"].replace("507", "508")
    lines[i] = json.dumps(rec)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert any("event 1" in p for p in validate_run(out, analyst_db))
