"""The agent loop: model <-> sandboxed SQL, ending in a structured answer."""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import duckdb

from analyst_eval.conditions import RECONCILE_FOLLOWUP, Condition, reconcile_prompt, system_prompt
from analyst_eval.questions import TOLERANCE, Question
from analyst_eval.reconcile import diff_results
from analyst_eval.runners import ModelRunner
from analyst_eval.sqlexec import execute, format_result, to_number
from analyst_eval.warehouse import connect_readonly


def reconcile_changed(rc: dict) -> bool:
    """Did reconciliation change the answer? Values are compared with a relative tolerance
    so the same number re-serialised with different float digits doesn't count."""
    if rc["final_status"] != rc["initial_status"]:
        return True
    a, b = rc["final_value"], rc["initial_value"]
    if a is None or b is None:
        return a is not b
    return not math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)

VALID_STATUS = ("answered", "answered_with_caveat", "abstained")
FORMAT_NUDGE = (
    "Reply with exactly one ```sql block to run a query, or exactly one ```json block "
    "with your final answer in the required format."
)
_SQL_RE = re.compile(r"```sql\s*\n(.*?)```", re.S | re.I)
_JSON_RE = re.compile(r"```json\s*\n(.*?)```", re.S | re.I)


@dataclass
class AgentConfig:
    max_sql: int = 8
    max_model_calls: int = 14
    max_format_errors: int = 2
    sql_timeout: float = 30.0


@dataclass
class AgentResult:
    question_id: str
    condition: str
    status: str  # one of VALID_STATUS, or "no_answer"
    value: float | None
    unit: str | None
    final_sql: str | None
    assumptions: list[str]
    checks: list[str]
    transcript: list[dict]
    input_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 0
    sql_calls: int = 0
    format_errors: int = 0
    value_matches_final_sql: bool | None = None
    reconcile: dict | None = None
    wall_seconds: float = 0.0
    error: str | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def parse_final(text: str) -> dict | None:
    m = _JSON_RE.search(text)
    raw = m.group(1) if m else text.strip()
    if not raw.startswith("{"):
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or obj.get("status") not in VALID_STATUS:
        return None
    return obj


def parse_sql(text: str) -> str | None:
    blocks = _SQL_RE.findall(text)
    if len(blocks) != 1:
        return None
    return blocks[0].strip() or None


def _as_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


class Agent:
    """Runs one question at a time. Each question gets a fresh read-only connection, so
    temp tables or views the model creates can't leak into later questions or conditions.
    ``setup`` runs on each new connection (tests use it to install helper views)."""

    def __init__(
        self,
        runner: ModelRunner,
        db_path: Path | str,
        condition: Condition,
        config: AgentConfig | None = None,
        setup: Callable[[duckdb.DuckDBPyConnection], None] | None = None,
    ):
        self.runner = runner
        self.db_path = db_path
        self.setup = setup
        self.condition = condition
        self.config = config or AgentConfig()
        self.system = system_prompt(condition, self.config.max_sql)

    def run(self, q: Question) -> AgentResult:
        self.con = connect_readonly(self.db_path)
        try:
            if self.setup:
                self.setup(self.con)
            return self._run(q)
        finally:
            self.con.close()

    def _run(self, q: Question) -> AgentResult:
        t0 = time.perf_counter()
        cfg = self.config
        messages: list[dict] = [{"role": "user", "content": f"Question: {q.question}"}]
        res = AgentResult(q.id, self.condition.name, "no_answer", None, None, None, [], [],
                          messages)
        final: dict | None = None
        reconciled = False
        try:
            while res.model_calls < cfg.max_model_calls:
                reply = self.runner.complete(self.system, messages)
                res.model_calls += 1
                res.input_tokens += reply.input_tokens
                res.output_tokens += reply.output_tokens
                res.extra.setdefault("turn_usage", []).append(
                    [reply.input_tokens, reply.output_tokens])
                messages.append({"role": "assistant", "content": reply.text})

                candidate = parse_final(reply.text)
                if candidate is not None:
                    final = candidate
                    if (self.condition.reconcile and not reconciled
                            and self._reconcilable(final)):
                        reconciled = True
                        res.reconcile = {"primary_sql": final.get("final_sql"),
                                         "initial_value": to_number(final.get("value")),
                                         "initial_status": final.get("status")}
                        messages.append({"role": "user", "content": reconcile_prompt()})
                        continue
                    break

                sql = parse_sql(reply.text)
                if sql is None:
                    res.format_errors += 1
                    if res.format_errors > cfg.max_format_errors:
                        break
                    messages.append({"role": "user", "content": FORMAT_NUDGE})
                    continue

                if res.reconcile is not None and "independent_sql" not in res.reconcile:
                    messages.append({"role": "user",
                                     "content": self._reconcile_diff(q, res, sql)})
                    continue

                if res.sql_calls >= cfg.max_sql:
                    messages.append({"role": "user", "content":
                                     "Query budget exhausted. Give your final ```json answer."})
                    continue
                res.sql_calls += 1
                out = execute(self.con, sql, cfg.sql_timeout)
                messages.append({"role": "user", "content": format_result(out)})
        except Exception as err:  # a runner failure must not lose the transcript
            res.error = f"{type(err).__name__}: {err}"

        if final is not None:
            res.status = final["status"]
            res.value = to_number(final.get("value"))
            res.unit = final.get("unit")
            res.final_sql = final.get("final_sql") or None
            res.assumptions = _as_list(final.get("assumptions"))
            res.checks = _as_list(final.get("checks"))
            if res.status != "abstained" and res.value is not None and res.final_sql:
                own = execute(self.con, res.final_sql, cfg.sql_timeout).scalar()
                tol = TOLERANCE.get(q.unit or "", 1e-6)
                res.value_matches_final_sql = own is not None and abs(own - res.value) <= tol
            if res.reconcile is not None:
                res.reconcile["final_value"] = res.value
                res.reconcile["final_status"] = res.status
                res.reconcile["changed"] = reconcile_changed(res.reconcile)
        res.wall_seconds = round(time.perf_counter() - t0, 3)
        return res

    @staticmethod
    def _reconcilable(final: dict) -> bool:
        return (final.get("status") != "abstained" and to_number(final.get("value")) is not None
                and bool(final.get("final_sql")))

    def _reconcile_diff(self, q: Question, res: AgentResult, independent_sql: str) -> str:
        cfg = self.config
        primary = execute(self.con, res.reconcile["primary_sql"], cfg.sql_timeout)
        independent = execute(self.con, independent_sql, cfg.sql_timeout)
        report = diff_results(primary, independent, TOLERANCE.get(q.unit or "", 1e-6))
        res.reconcile["independent_sql"] = independent_sql
        res.reconcile["match"] = report.match
        res.reconcile["diff"] = report.details
        body = (f"{report.summary}\n\nPrimary result:\n{format_result(primary)}\n\n"
                f"Independent result:\n{format_result(independent)}")
        return RECONCILE_FOLLOWUP.format(report=body)
