"""Run the evaluation, persist runs as JSONL, and validate saved runs offline.

A saved run is a ``meta`` line, one ``answer`` line per (condition, question, trial), and
an ``end`` line. Validation re-executes every saved transcript against a freshly built
warehouse with a ``ReplayRunner``: the model's words are taken from the file, but every
SQL result, reconciliation diff and parsed answer is recomputed and must match. Tool
output is compared after canonicalisation (line order ignored, numbers rounded to six
decimals) so that unordered result sets and float noise don't cause false failures.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import duckdb

from analyst_eval import RUNS_DIR
from analyst_eval.agent import Agent, AgentConfig, AgentResult
from analyst_eval.answer_key import ANSWER_KEY_PATH
from analyst_eval.conditions import CONDITIONS, prompt_hash, system_prompt
from analyst_eval.questions import QUESTIONS_BY_ID, Question
from analyst_eval.runners import Completion, ModelRunner, Pricing, ReplayExhausted, ReplayRunner
from analyst_eval.warehouse import DEFAULT_N_USERS, DEFAULT_SEED

Setup = Callable[[duckdb.DuckDBPyConnection], None]
SCHEMA_VERSION = 1
ANSWER_FIELDS = (
    "question_id", "condition", "trial", "status", "value", "unit", "final_sql", "assumptions",
    "checks", "transcript", "input_tokens", "output_tokens", "model_calls", "sql_calls",
    "format_errors", "value_matches_final_sql", "reconcile", "error", "extra",
)
# Fields recomputed by replay and required to match the saved record.
REPLAYED_FIELDS = (
    "status", "value", "unit", "final_sql", "sql_calls", "format_errors",
    "value_matches_final_sql", "reconcile", "input_tokens", "output_tokens", "model_calls",
)
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:e[-+]?\d+)?(?![\w.])", re.I)


def _canonical(text: str) -> list[str]:
    lines = (_NUMBER.sub(lambda m: f"{round(float(m.group()), 6):.6f}", ln)
             for ln in text.splitlines())
    return sorted(ln.rstrip() for ln in lines)


def canonical_transcript(transcript: list[dict]) -> list[tuple[str, list[str]]]:
    return [(m["role"], _canonical(m["content"])) for m in transcript]


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16]


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                             check=True, timeout=10)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def build_meta(runner: ModelRunner, conditions: list[str], trials: int, config: AgentConfig,
               pricing: Pricing | None, base_url: str | None = None) -> dict:
    started = datetime.now(timezone.utc)
    return {
        "type": "meta",
        "schema_version": SCHEMA_VERSION,
        "run_id": f"{started:%Y%m%dT%H%M%SZ}_{runner.provider}_{runner.model}".replace("/", "-"),
        "provider": runner.provider,
        "model": runner.model,
        "endpoint_host": urlparse(base_url).hostname if base_url else None,
        "temperature": getattr(runner, "temperature", None),
        "started_at": started.isoformat(),
        "git_commit": _git_commit(),
        "conditions": {c: prompt_hash(CONDITIONS[c], config.max_sql) for c in conditions},
        "answer_key_sha": file_sha(ANSWER_KEY_PATH),
        "agent_config": asdict(config),
        "trials": trials,
        "pricing": asdict(pricing) if pricing else None,
        "dataset": {"n_users": DEFAULT_N_USERS, "seed": DEFAULT_SEED},
    }


def run_eval(
    runner: ModelRunner,
    db_path: Path | str,
    questions: list[Question],
    conditions: list[str],
    trials: int,
    out_path: Path,
    config: AgentConfig | None = None,
    pricing: Pricing | None = None,
    max_cost_usd: float | None = None,
    base_url: str | None = None,
    log=print,
    setup: Setup | None = None,
) -> Path:
    config = config or AgentConfig()
    meta = build_meta(runner, conditions, trials, config, pricing, base_url)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tin = tout = 0
    stopped = None
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(meta) + "\n")
        for trial in range(trials):
            for cname in conditions:
                agent = Agent(runner, db_path, CONDITIONS[cname], config, setup)
                for q in questions:
                    res = agent.run(q)
                    rec = {"type": "answer", "trial": trial, **_answer_fields(res)}
                    fh.write(json.dumps(rec, default=str) + "\n")
                    fh.flush()
                    tin += res.input_tokens
                    tout += res.output_tokens
                    spent = pricing.cost(tin, tout) if pricing else None
                    log(f"[{cname} t{trial}] {q.id}: {res.status} {res.value} "
                        f"({res.model_calls} calls" + (f", ${spent:.2f} so far)" if spent
                                                       is not None else ")"))
                    if max_cost_usd is not None and spent is not None and spent >= max_cost_usd:
                        stopped = f"budget ${max_cost_usd:.2f} reached"
                        break
                if stopped:
                    break
            if stopped:
                break
        end = {"type": "end", "finished_at": datetime.now(timezone.utc).isoformat(),
               "input_tokens": tin, "output_tokens": tout, "stopped": stopped}
        fh.write(json.dumps(end) + "\n")
    return out_path


def _answer_fields(res: AgentResult) -> dict:
    d = res.to_dict()
    return {k: d[k] for k in ANSWER_FIELDS if k in d}


def load_run(path: Path) -> tuple[dict, list[dict], dict | None]:
    meta, answers, end = None, [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("type") == "meta":
            meta = rec
        elif rec.get("type") == "answer":
            answers.append(rec)
        elif rec.get("type") == "end":
            end = rec
    if meta is None:
        raise ValueError(f"{path.name}: no meta line")
    return meta, answers, end


def list_runs(runs_dir: Path = RUNS_DIR) -> list[Path]:
    return sorted(runs_dir.glob("*.jsonl"))


def replay_answer(rec: dict, meta: dict, db_path: Path | str,
                  setup: Setup | None = None) -> list[str]:
    """Re-execute one saved answer; return a list of mismatches (empty = valid)."""
    turns = [m["content"] for m in rec["transcript"] if m["role"] == "assistant"]
    usage = rec.get("extra", {}).get("turn_usage") or [[0, 0]] * len(turns)
    if len(usage) != len(turns):
        return ["turn_usage length does not match assistant turns"]
    runner = ReplayRunner([Completion(t, u[0], u[1]) for t, u in zip(turns, usage, strict=True)],
                          model=meta["model"])
    config = AgentConfig(**meta["agent_config"])
    agent = Agent(runner, db_path, CONDITIONS[rec["condition"]], config, setup)
    res = agent.run(QUESTIONS_BY_ID[rec["question_id"]])
    fresh = _answer_fields(res)
    problems = []
    if rec.get("error"):
        # The original call failed mid-question (e.g. a network error). Replay should run
        # out of saved turns at exactly the same point.
        if not (res.error or "").startswith(ReplayExhausted.__name__):
            problems.append(f"saved run stopped with an error but replay did not: {res.error}")
    elif res.error:
        problems.append(f"replay error: {res.error}")
    if not runner.exhausted:
        problems.append("replay finished before all saved assistant turns were used")
    if canonical_transcript(res.transcript) != canonical_transcript(rec["transcript"]):
        problems.append("field 'transcript' differs on replay")
    for k in REPLAYED_FIELDS:
        if json.loads(json.dumps(fresh.get(k), default=str)) != rec.get(k):
            problems.append(f"field {k!r} differs on replay")
    return problems


def validate_run(path: Path, db_path: Path | str, setup: Setup | None = None) -> list[str]:
    meta, answers, end = load_run(path)
    problems = []
    if meta.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version {meta.get('schema_version')} != {SCHEMA_VERSION}")
    if meta.get("answer_key_sha") != file_sha(ANSWER_KEY_PATH):
        problems.append("answer key changed since this run")
    max_sql = meta["agent_config"]["max_sql"]
    for cname, h in meta["conditions"].items():
        if cname not in CONDITIONS:
            problems.append(f"unknown condition {cname}")
        elif prompt_hash(CONDITIONS[cname], max_sql) != h:
            problems.append(f"prompt for {cname} changed since this run (context or skill edited)")
    if end is None:
        problems.append("run has no end line (interrupted)")
    for rec in answers:
        tag = f"{rec.get('condition')}/{rec.get('question_id')}/t{rec.get('trial')}"
        missing = [k for k in ANSWER_FIELDS if k not in rec]
        if missing:
            problems.append(f"{tag}: missing fields {missing}")
            continue
        if rec["question_id"] not in QUESTIONS_BY_ID or rec["condition"] not in meta["conditions"]:
            problems.append(f"{tag}: unknown question or condition")
            continue
        problems += [f"{tag}: {p}" for p in replay_answer(rec, meta, db_path, setup)]
    return [f"{path.name}: {p}" for p in problems]


def estimate_tokens(conditions: list[str], n_questions: int, trials: int,
                    config: AgentConfig | None = None, calls_per_q: float = 5.0,
                    tokens_per_turn: int = 350) -> dict[str, dict[str, float]]:
    """Rough pre-flight token estimate (chars/4 heuristic); not a substitute for a pilot."""
    config = config or AgentConfig()
    out = {}
    for c in conditions:
        cond = CONDITIONS[c]
        sys_tokens = len(system_prompt(cond, config.max_sql)) / 4
        calls = calls_per_q + (2 if cond.reconcile else 0)
        per_q_in = calls * sys_tokens + tokens_per_turn * calls * (calls + 1) / 2
        per_q_out = calls * 250
        n = n_questions * trials
        out[c] = {"system_prompt_tokens": sys_tokens, "input_tokens": per_q_in * n,
                  "output_tokens": per_q_out * n}
    return out
