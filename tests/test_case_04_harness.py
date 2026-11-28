"""Case 04: harness logic -- agent loop, reconciliation, grading, replay validation, memo lint.

Scripted runners here exist to test the harness. They are not models and their scores are
not results.
"""

from __future__ import annotations

import json
import re

import duckdb
import pytest
from analyst_eval import CASE_DIR
from analyst_eval.agent import Agent, AgentConfig, parse_final, parse_sql
from analyst_eval.answer_key import load_answer_key
from analyst_eval.conditions import CONDITIONS, CORE_CONDITIONS, system_prompt
from analyst_eval.evidence import load_evidence
from analyst_eval.gold import create_gold_views
from analyst_eval.grading import grade_answer, summarize
from analyst_eval.memo_lint import lint_memo, numbers_in
from analyst_eval.questions import QUESTIONS, QUESTIONS_BY_ID
from analyst_eval.reconcile import diff_results
from analyst_eval.report import PENDING, SUMMARY_JSON, SUMMARY_MD, summarize_runs
from analyst_eval.runners import CallableRunner, Pricing
from analyst_eval.runs import engine_mismatch, list_runs, load_run, run_eval, validate_run
from analyst_eval.sqlexec import QueryResult
from analyst_eval.warehouse import connect_readonly

KEY = load_answer_key()
KEY_EVIDENCE_REFUNDS = int(load_evidence()["n_refunds"]["value"])
BY_TEXT = {q.question: q for q in QUESTIONS}


@pytest.fixture()
def agent_for(analyst_db):
    """Agent factory; gold views are installed on each fresh connection so scripted
    runners can use them as their SQL."""

    def make(runner, condition: str, config: AgentConfig | None = None) -> Agent:
        return Agent(runner, analyst_db, CONDITIONS[condition], config, create_gold_views)

    return make


def _json_block(obj: dict) -> str:
    return "```json\n" + json.dumps(obj) + "\n```"


def scripted(sql_attr: str, value_attr: str, flip_first: bool = False):
    """A runner that answers with a question's gold or naive SQL. ``flip_first`` makes it
    submit the naive answer first and fix it after a reconciliation mismatch."""

    def fn(system: str, messages: list[dict]) -> str:
        q = BY_TEXT[messages[0]["content"].removeprefix("Question: ")]
        last = messages[-1]["content"] if messages[-1]["role"] == "user" else ""
        n_assistant = sum(m["role"] == "assistant" for m in messages)
        sql = getattr(q, sql_attr)
        value = KEY[q.id][value_attr]
        if last.startswith("RECONCILE STEP"):
            return f"```sql\n{q.gold_sql}\n```"
        if last.startswith("Data-diff"):
            return _json_block({"status": "answered", "value": KEY[q.id]["gold"],
                                "unit": q.unit, "final_sql": q.gold_sql})
        if sql is None:
            return _json_block({"status": "abstained", "value": None,
                                "assumptions": ["not answerable"]})
        if n_assistant == 0:
            return f"Checking.\n```sql\n{q.naive_sql if flip_first else sql}\n```"
        if flip_first:
            return _json_block({"status": "answered", "value": KEY[q.id]["naive"],
                                "unit": q.unit, "final_sql": q.naive_sql})
        return _json_block({"status": "answered", "value": value, "unit": q.unit,
                            "final_sql": sql})

    return fn


def _run_all(agent_for, condition: str, runner) -> list[dict]:
    agent = agent_for(runner, condition)
    return [{**agent.run(q).to_dict(), "trial": 0} for q in QUESTIONS]


def test_oracle_runner_scores_every_question_correct(agent_for):
    answers = _run_all(agent_for, "full_context", CallableRunner(scripted("gold_sql", "gold")))
    grades = [grade_answer(a, KEY[a["question_id"]]) for a in answers]
    assert [g.question_id for g in grades if not g.correct] == []
    assert all(a["value_matches_final_sql"] for a in answers if a["status"] == "answered")


def test_naive_runner_is_right_only_where_no_trap_bites(agent_for):
    answers = _run_all(agent_for, "no_context", CallableRunner(scripted("naive_sql", "naive")))
    grades = [grade_answer(a, KEY[a["question_id"]]) for a in answers]
    correct = {g.question_id for g in grades if g.correct}
    expected = {q.id for q in QUESTIONS
                if q.category == "control" or (q.expect_abstain and q.naive_sql is None)}
    assert correct == expected
    summary = summarize(grades, KEY)["conditions"]["no_context"]
    assert summary["confidently_wrong_rate"] == pytest.approx(30 / 40)
    # 27 answerable questions plus 3 unanswerable ones where a naive number was produced
    assert summary["fell_for_naive_rate"] == pytest.approx(30 / 40)
    assert summary["accuracy_by_category"]["control"] == 1.0


def test_reconcile_step_diffs_independent_route_and_records_the_fix(agent_for):
    q = QUESTIONS_BY_ID["t01"]
    agent = agent_for(CallableRunner(scripted("gold_sql", "gold", flip_first=True)),
                      "full_context_reconcile")
    res = agent.run(q)
    assert res.reconcile["initial_value"] == KEY["t01"]["naive"]
    assert res.reconcile["match"] is False
    assert res.reconcile["changed"] is True
    assert res.value == KEY["t01"]["gold"]
    assert any(m["content"].startswith("Data-diff") and "MISMATCH" in m["content"]
               for m in res.transcript)


def test_non_reconcile_conditions_never_get_a_reconcile_step(agent_for):
    for cond in ("no_context", "schema_only", "full_context"):
        res = agent_for(CallableRunner(scripted("gold_sql", "gold")), cond).run(
            QUESTIONS_BY_ID["t01"])
        assert res.reconcile is None


def test_format_failures_end_as_no_answer(agent_for):
    res = agent_for(CallableRunner(lambda s, m: "I think it's about 4,000."), "no_context",
                    AgentConfig(max_format_errors=2)).run(QUESTIONS[0])
    assert (res.status, res.format_errors, res.model_calls) == ("no_answer", 3, 3)
    assert grade_answer({**res.to_dict(), "trial": 0}, KEY[QUESTIONS[0].id]).outcome == "no_answer"


def test_sql_budget_is_enforced(agent_for):
    res = agent_for(CallableRunner(lambda s, m: "```sql\nSELECT 1\n```"), "no_context",
                    AgentConfig(max_sql=3, max_model_calls=6)).run(QUESTIONS[0])
    assert res.sql_calls == 3 and res.model_calls == 6 and res.status == "no_answer"


def test_sandbox_blocks_writes_and_file_access(analyst_db):
    from analyst_eval.sqlexec import execute

    con = connect_readonly(analyst_db)
    try:
        for sql in ("CREATE TABLE x (a INT)", "COPY users TO 'leak.csv'",
                    "SELECT * FROM read_csv('leak.csv')", "SET enable_external_access = true"):
            assert not execute(con, sql).ok, sql
    finally:
        con.close()


def test_parsers():
    assert parse_sql("x\n```sql\nSELECT 1\n```") == "SELECT 1"
    assert parse_sql("```sql\nSELECT 1\n```\n```sql\nSELECT 2\n```") is None
    assert parse_final('```json\n{"status": "abstained", "value": null}\n```')["status"]
    assert parse_final('```json\n{"status": "maybe", "value": 1}\n```') is None
    assert parse_final("not json") is None


def test_every_condition_has_the_same_protocol_and_no_gold_leaks():
    prompts = {c: system_prompt(CONDITIONS[c], 8) for c in CONDITIONS}
    for c, p in prompts.items():
        assert '"abstained"' in p, c
        assert not re.search(r"\bg_(events|orders|users)\b", p), c
        for q in QUESTIONS:
            assert q.question not in p, (c, q.id)
    assert len(prompts["no_context"]) < len(prompts["schema_only"]) < len(prompts["full_context"])
    assert prompts["full_context"] == prompts["full_context_reconcile"]
    assert CORE_CONDITIONS == ["no_context", "schema_only", "full_context",
                               "full_context_reconcile"]


def _qr(cols, rows):
    return QueryResult(cols, rows)


def test_diff_results_scalar_and_keyed():
    assert diff_results(_qr(["a"], [(10,)]), _qr(["b"], [(10.2,)]), 0.5).match
    assert not diff_results(_qr(["a"], [(10,)]), _qr(["b"], [(11,)]), 0.5).match
    left = _qr(["d", "n"], [("2025-01-01", 5), ("2025-01-02", 7)])
    right = _qr(["day", "cnt"], [("2025-01-01", 5), ("2025-01-03", 7)])
    rep = diff_results(left, right)
    assert not rep.match and rep.details["only_left"] == 1 and rep.details["only_right"] == 1
    assert not diff_results(_qr(["a"], [(1,)]), _qr(["a", "b"], [(1, 2)])).match
    assert not diff_results(QueryResult(error="boom"), _qr(["a"], [(1,)])).match


def test_grading_outcomes():
    t01, u04 = KEY["t01"], KEY["u04"]

    def g(row, **kw):
        return grade_answer({"question_id": row["id"], "condition": "c", **kw}, row)

    assert g(t01, status="answered", value=t01["gold"] + 0.4).outcome == "correct"
    assert g(t01, status="answered", value=t01["naive"]).outcome == "confidently_wrong"
    assert g(t01, status="answered", value=t01["naive"]).fell_for_naive
    assert g(t01, status="answered_with_caveat", value=1).outcome == "caveated_wrong"
    assert g(t01, status="abstained", value=None).outcome == "over_abstained"
    assert g(u04, status="abstained", value=None).outcome == "correct"
    assert g(u04, status="answered", value=45907).outcome == "confidently_wrong"
    t18 = KEY["t18"]  # largest order: cents instead of dollars
    assert g(t18, status="answered", value=t18["gold"] * 100).unit_slip


def test_summary_costs_and_lift():
    t01 = KEY["t01"]
    grades = [grade_answer({"question_id": "t01", "condition": c, "status": "answered",
                            "value": v, "input_tokens": 1000, "output_tokens": 100}, t01)
              for c, v in (("no_context", t01["naive"]), ("full_context", t01["gold"]))]
    s = summarize(grades, KEY, Pricing(3.0, 15.0))["conditions"]
    assert s["full_context"]["cost_usd_per_q"] == pytest.approx(0.0045)
    assert s["no_context"]["cost_usd_per_correct"] is None
    assert s["full_context"]["accuracy_lift_vs_baseline"]["mean"] == 1.0


def test_saved_run_replays_and_tampering_is_caught(analyst_db, tmp_path):
    path = tmp_path / "run.jsonl"
    qs = [QUESTIONS_BY_ID[i] for i in ("c01", "t01", "u02")]
    runner = CallableRunner(scripted("gold_sql", "gold", flip_first=True), model="scripted")
    run_eval(runner, analyst_db, qs, ["no_context", "full_context_reconcile"], 1, path,
             log=lambda *_: None, setup=create_gold_views)
    assert validate_run(path, analyst_db, create_gold_views) == []

    lines = path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[2])  # no_context / t01
    for m in rec["transcript"]:
        if m["role"] == "user" and "rows, showing" in m["content"]:
            m["content"] = re.sub(r"\d+", "1", m["content"])
            break
    lines[2] = json.dumps(rec)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    problems = validate_run(path, analyst_db, create_gold_views)
    assert any("transcript" in p for p in problems)


def _explorer(system: str, messages: list[dict]) -> str:
    n = sum(m["role"] == "assistant" for m in messages)
    if n == 0:
        return "```sql\nSELECT event_name, COUNT(*) FROM events GROUP BY 1\n```"
    if n == 1:
        return "```sql\nSELECT SUM(revenue_cents / 100.0) FROM events\n```"
    return _json_block({"status": "abstained", "value": None})


def test_replay_ignores_row_order_and_float_noise(analyst_db, tmp_path):
    path = tmp_path / "run.jsonl"
    run_eval(CallableRunner(_explorer), analyst_db, [QUESTIONS_BY_ID["c01"]], ["no_context"], 1,
             path, log=lambda *_: None)
    lines = path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[1])
    grouped, total = (m for m in rec["transcript"] if "rows, showing" in m["content"])
    body = grouped["content"].splitlines()
    grouped["content"] = "\n".join([body[0], *reversed(body[1:-1]), body[-1]])
    total["content"] = re.sub(r"(\d+\.\d+)", lambda m: repr(float(m.group()) + 1e-9),
                              total["content"])
    lines[1] = json.dumps(rec)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert validate_run(path, analyst_db) == []


def test_temp_objects_do_not_leak_between_questions(analyst_db, tmp_path):
    def fn(system: str, messages: list[dict]) -> str:
        first_q = messages[0]["content"].endswith(QUESTIONS_BY_ID["c01"].question)
        if sum(m["role"] == "assistant" for m in messages) == 0:
            sql = ("CREATE TEMP VIEW refunds AS SELECT 1 AS x" if first_q
                   else "SELECT COUNT(*) AS n FROM refunds")
            return f"```sql\n{sql}\n```"
        return _json_block({"status": "abstained", "value": None})

    path = tmp_path / "run.jsonl"
    run_eval(CallableRunner(fn), analyst_db, [QUESTIONS_BY_ID["c01"], QUESTIONS_BY_ID["c02"]],
             ["no_context", "schema_only"], 1, path, log=lambda *_: None)
    _, answers, _ = load_run(path)
    for a in answers:
        tool = a["transcript"][2]["content"]
        if a["question_id"] == "c01":
            assert not tool.startswith("ERROR"), tool  # a repeat must not clash with a leak
        else:
            assert tool.splitlines()[1] == str(KEY_EVIDENCE_REFUNDS)
    assert validate_run(path, analyst_db) == []


def test_run_interrupted_by_a_provider_error_still_validates(analyst_db, tmp_path):
    def fn(system: str, messages: list[dict]) -> str:
        if sum(m["role"] == "assistant" for m in messages) == 0:
            return "```sql\nSELECT 1\n```"
        raise TimeoutError("provider timed out")

    path = tmp_path / "run.jsonl"
    run_eval(CallableRunner(fn), analyst_db, [QUESTIONS_BY_ID["c01"]], ["no_context"], 1, path,
             log=lambda *_: None)
    _, answers, _ = load_run(path)
    assert answers[0]["error"].startswith("TimeoutError")
    assert answers[0]["status"] == "no_answer"
    assert validate_run(path, analyst_db) == []


def test_memo_lint():
    ev = {"a": {"value": 7.1334, "checks": ["x"]}, "b": {"value": -41.36, "checks": ["x"]},
          "c": {"value": 122665.44, "checks": []}}
    doc = "\n".join([
        "<!-- cited:start -->",
        "Refund rate was 7.1% [E:a].",
        "DAU fell 41% [E:b] on 2025-03-31 at 18:00 for question t06.",
        "Refund rate was 7.2% [E:a].",
        "Revenue was $122,665 [E:c].",
        "Something rose 12%.",
        "See [E:missing].",
        "<!-- cited:end -->",
    ])
    problems = [i.problem for i in lint_memo(doc, ev)]
    assert len(problems) == 4
    assert "does not match" in problems[0]
    assert "no checks" in problems[1]
    assert "without an [E:...] citation" in problems[2]
    assert "unknown evidence" in problems[3]
    assert numbers_in("W1 cohort on 2025-01-06, -3.5x and $1,200.50") == [(-3.5, 1),
                                                                          (1200.5, 2)]


def test_saved_runs_are_valid_and_results_are_current(analyst_db):
    paths = list_runs()
    if not paths:
        assert SUMMARY_MD.read_text(encoding="utf-8") == PENDING
        assert "Results pending" in (CASE_DIR / "README.md").read_text(encoding="utf-8")
        return
    committed = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
    assert json.loads(json.dumps(summarize_runs(paths), sort_keys=True)) == committed
    unreplayable = {p.name: m for p in paths if (m := engine_mismatch(load_run(p)[0]))}
    replayable = [p for p in paths if p.name not in unreplayable]
    problems = [p for path in replayable for p in validate_run(path, analyst_db)]
    assert not problems, "\n".join(problems)
    if unreplayable:
        pytest.skip(f"replay needs the recording engine: {unreplayable}")


def test_engine_mismatch_blocks_replay_instead_of_reporting_tampering():
    from analyst_eval.runs import LEGACY_AGENT_ENGINE, recorded_engine

    here = duckdb.__version__
    other = f"{int(here.split('.')[0]) + 1}.0.0"
    assert engine_mismatch({"engine": {"duckdb": here}}) is None
    assert "different major" in engine_mismatch({"engine": {"duckdb": other}})
    assert recorded_engine({"runner_kind": "copilot-agent"}) == LEGACY_AGENT_ENGINE
    assert recorded_engine({}) is None


def test_volatile_sql_detection():
    from analyst_eval.runs import is_volatile

    assert is_volatile("SELECT current_date, COUNT(*) FROM users")
    assert is_volatile("select now() - max(event_ts) from events")
    assert is_volatile("SELECT random() < 0.5")
    assert not is_volatile("SELECT 'today' AS label, COUNT(*) AS today_n FROM users")
    assert not is_volatile("SELECT COUNT(*) FROM events WHERE event_name = 'now()'")
    assert not is_volatile(None)


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
def test_live_runners_speak_their_wire_format(kind, monkeypatch):
    """Offline: a local stub stands in for the provider, so no key or spend is involved."""
    import http.server
    import threading

    from analyst_eval.runners import AnthropicRunner, OpenAICompatibleRunner

    seen = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            seen["path"] = self.path
            seen["headers"] = self.headers
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if kind == "openai":
                out = {"choices": [{"message": {"content": "hi"}}],
                       "usage": {"prompt_tokens": 11, "completion_tokens": 2}}
            else:
                out = {"content": [{"type": "text", "text": "hi"}],
                       "usage": {"input_tokens": 11, "output_tokens": 2}}
            data = json.dumps(out).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/v1"
    monkeypatch.setenv("TEST_KEY", "sk-test")
    try:
        if kind == "openai":
            runner = OpenAICompatibleRunner("m", base_url=base, api_key_env="TEST_KEY")
        else:
            runner = AnthropicRunner("m", base_url=base, api_key_env="TEST_KEY")
        c = runner.complete("SYS", [{"role": "user", "content": "Q"}])
    finally:
        server.shutdown()
    assert (c.text, c.input_tokens, c.output_tokens) == ("hi", 11, 2)
    assert seen["body"]["temperature"] == 0.0
    if kind == "openai":
        assert seen["path"] == "/v1/chat/completions"
        assert seen["headers"].get("authorization") == "Bearer sk-test"
        assert seen["body"]["messages"][0] == {"role": "system", "content": "SYS"}
    else:
        assert seen["path"] == "/v1/messages"
        assert seen["headers"].get("x-api-key") == "sk-test"
        assert seen["body"]["system"] == "SYS"


def test_report_pools_trials_by_model_and_rejects_duplicates(analyst_db, tmp_path):
    runner = CallableRunner(scripted("gold_sql", "gold"), model="scripted")
    qs = [QUESTIONS_BY_ID["c01"], QUESTIONS_BY_ID["t01"]]
    two_trials = run_eval(runner, analyst_db, qs, ["full_context"], 2, tmp_path / "a.jsonl",
                          log=lambda *_: None, setup=create_gold_views)
    other_cond = run_eval(runner, analyst_db, qs, ["no_context"], 1, tmp_path / "b.jsonl",
                          log=lambda *_: None, setup=create_gold_views)
    (run,) = summarize_runs([two_trials, other_cond])["runs"]
    assert run["files"] == ["a.jsonl", "b.jsonl"] and run["trials"] == [0, 1]
    assert run["conditions"]["full_context"]["n_answers"] == 4
    assert run["conditions"]["full_context"]["same_outcome_across_trials"] == 1.0
    assert "same_outcome_across_trials" not in run["conditions"]["no_context"]
    dup = run_eval(runner, analyst_db, qs, ["no_context"], 1, tmp_path / "c.jsonl",
                   log=lambda *_: None, setup=create_gold_views)
    with pytest.raises(ValueError, match="more than once"):
        summarize_runs([other_cond, dup])
