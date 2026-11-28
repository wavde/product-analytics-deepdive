"""Command line for case study 04. Run from the case directory:

    python src/cli.py build          # warehouse + answer key + evidence
    python src/cli.py plan  --questions all --trials 1 [--price-in 3 --price-out 15]
    python src/cli.py run   --provider anthropic --model <id> --price-in .. --price-out ..
                            --max-cost-usd 5 [--conditions core] [--trials 1]
    python src/cli.py validate       # replay every saved run offline
    python src/cli.py report         # results/summary.{json,md} from saved runs
    python src/cli.py lint-memo      # check README numbers against results/evidence.json
    python src/cli.py bundle --root <dir outside repo> --python <python with duckdb>
    python src/cli.py import-agent-run --root <dir> --model <id> --out <name>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyst_eval import CASE_DIR, DB_PATH, HOLDOUT_DB_PATH, RUNS_DIR  # noqa: E402
from analyst_eval.agent import AgentConfig  # noqa: E402
from analyst_eval.answer_key import (  # noqa: E402
    HOLDOUT_KEY_PATH,
    VARIANTS,
    compute_answer_key,
    write_answer_key,
)
from analyst_eval.conditions import CONDITIONS, CORE_CONDITIONS  # noqa: E402
from analyst_eval.evidence import build_evidence, load_evidence, write_evidence  # noqa: E402
from analyst_eval.memo_lint import lint_memo  # noqa: E402
from analyst_eval.questions import HOLDOUT_QUESTIONS, QUESTIONS, QUESTIONS_BY_ID  # noqa: E402
from analyst_eval.report import write_summary  # noqa: E402
from analyst_eval.runners import AnthropicRunner, OpenAICompatibleRunner, Pricing  # noqa: E402
from analyst_eval.runs import estimate_tokens, list_runs, run_eval, validate_run  # noqa: E402
from analyst_eval.warehouse import build, build_holdout  # noqa: E402


def _conditions(arg: str) -> list[str]:
    if arg == "core":
        return CORE_CONDITIONS
    if arg == "all":
        return list(CONDITIONS)
    names = [c.strip() for c in arg.split(",")]
    unknown = [c for c in names if c not in CONDITIONS]
    if unknown:
        raise SystemExit(f"Unknown conditions {unknown}; choose from {list(CONDITIONS)}")
    return names


def _questions(arg: str):
    if arg == "all":
        return QUESTIONS
    return [QUESTIONS_BY_ID[q.strip()] for q in arg.split(",")]


def _pricing(args) -> Pricing | None:
    if args.price_in is None and args.price_out is None:
        return None
    if args.price_in is None or args.price_out is None:
        raise SystemExit("Give both --price-in and --price-out (USD per million tokens).")
    return Pricing(args.price_in, args.price_out)


def cmd_build(_args) -> None:
    build()
    build_holdout()
    write_answer_key(compute_answer_key())
    write_answer_key(compute_answer_key(HOLDOUT_DB_PATH, HOLDOUT_QUESTIONS), HOLDOUT_KEY_PATH)
    write_evidence(build_evidence())
    print(f"Built {DB_PATH.name}, {HOLDOUT_DB_PATH.name}, their answer keys and "
          "results/evidence.json")


def cmd_plan(args) -> None:
    conds, qs, pricing = _conditions(args.conditions), _questions(args.questions), _pricing(args)
    est = estimate_tokens(conds, len(qs), args.trials)
    tin = tout = 0.0
    print(f"{len(qs)} questions x {args.trials} trial(s). Rough estimate (chars/4):")
    for c, e in est.items():
        tin += e["input_tokens"]
        tout += e["output_tokens"]
        print(f"  {c:24s} system prompt ~{e['system_prompt_tokens']:,.0f} tok; "
              f"~{e['input_tokens']:,.0f} in / ~{e['output_tokens']:,.0f} out")
    print(f"  {'total':24s} ~{tin:,.0f} in / ~{tout:,.0f} out")
    if pricing:
        print(f"  estimated cost ~${pricing.cost(int(tin), int(tout)):.2f}")


def cmd_run(args) -> None:
    pricing = _pricing(args)
    if pricing is None or args.max_cost_usd is None:
        raise SystemExit("Live runs need --price-in, --price-out and --max-cost-usd so the "
                         "budget guard can stop the run.")
    if args.provider == "anthropic":
        runner = AnthropicRunner(model=args.model, temperature=args.temperature)
    else:
        runner = OpenAICompatibleRunner(model=args.model, base_url=args.base_url,
                                        api_key_env=args.api_key_env,
                                        temperature=args.temperature)
    if not DB_PATH.exists():
        cmd_build(args)
    out = RUNS_DIR / f"{args.out or 'run'}_{args.provider}_{args.model}.jsonl".replace("/", "-")
    if out.exists() and not args.overwrite:
        raise SystemExit(f"{out} exists; pass --out NAME or --overwrite.")
    run_eval(runner, DB_PATH, _questions(args.questions), _conditions(args.conditions),
             args.trials, out, AgentConfig(), pricing, args.max_cost_usd,
             base_url=args.base_url if args.provider != "anthropic" else None)
    print(f"Saved {out}")


def cmd_validate(_args) -> None:
    paths = list_runs()
    if not paths:
        print("No saved runs to validate.")
        return
    if not DB_PATH.exists() or not HOLDOUT_DB_PATH.exists():
        cmd_build(_args)
    problems = [p for path in paths for p in validate_run(path, DB_PATH)]
    for p in problems:
        print(p)
    if problems:
        raise SystemExit(1)
    print(f"{len(paths)} run(s) valid.")


def cmd_report(_args) -> None:
    summary = write_summary(list_runs())
    print(f"Summarised {len(summary['runs'])} run(s) into results/summary.md")


def cmd_lint_memo(args) -> None:
    text = (CASE_DIR / "README.md").read_text(encoding="utf-8")
    issues = lint_memo(text, load_evidence())
    for i in issues:
        print(i)
    if issues:
        raise SystemExit(1)
    print("README claims all match cited evidence.")


def cmd_bundle(args) -> None:
    from analyst_eval.agent_runs import build_bundles

    if not DB_PATH.exists() or not HOLDOUT_DB_PATH.exists():
        cmd_build(args)
    questions = (VARIANTS[args.variant]["questions"] if args.questions == "all"
                 else _questions(args.questions))
    m = build_bundles(Path(args.root), _conditions(args.conditions), questions,
                      args.python, variant=args.variant)
    print(f"Wrote {len(m['conditions'])} blind {args.variant} bundle(s) for "
          f"{len(m['questions'])} question(s) under {args.root}")


def cmd_import_agent_run(args) -> None:
    from analyst_eval.agent_runs import import_bundles

    out = RUNS_DIR / f"{args.out}_github-copilot_{args.model}.jsonl"
    if out.exists() and not args.overwrite:
        raise SystemExit(f"{out} exists; pass --overwrite.")
    import_bundles(Path(args.root), args.model, out,
                   questions=None if args.questions == "all" else args.questions.split(","),
                   trial=args.trial)
    problems = validate_run(out, DB_PATH)
    for p in problems:
        print(p)
    if problems:
        raise SystemExit(1)
    print(f"Imported and validated {out}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build").set_defaults(fn=cmd_build)
    for name, fn in (("plan", cmd_plan), ("run", cmd_run)):
        sp = sub.add_parser(name)
        sp.add_argument("--conditions", default="core", help="core | all | comma list")
        sp.add_argument("--questions", default="all", help="all | comma list of ids")
        sp.add_argument("--trials", type=int, default=1)
        sp.add_argument("--price-in", type=float, help="USD per 1M input tokens")
        sp.add_argument("--price-out", type=float, help="USD per 1M output tokens")
        sp.set_defaults(fn=fn)
        if name == "run":
            sp.add_argument("--provider", choices=["anthropic", "openai-compatible"],
                            required=True)
            sp.add_argument("--model", required=True)
            sp.add_argument("--base-url", default="https://api.openai.com/v1")
            sp.add_argument("--api-key-env", default="OPENAI_API_KEY")
            sp.add_argument("--temperature", type=float, default=0.0)
            sp.add_argument("--max-cost-usd", type=float)
            sp.add_argument("--out", help="file name prefix under runs/")
            sp.add_argument("--overwrite", action="store_true")
    sub.add_parser("validate").set_defaults(fn=cmd_validate)
    sp = sub.add_parser("bundle", help="blind folders for Copilot-agent runs")
    sp.add_argument("--root", required=True, help="output folder, outside the repo")
    sp.add_argument("--python", required=True, help="python with duckdb, for the agents")
    sp.add_argument("--conditions", default="core")
    sp.add_argument("--questions", default="all")
    sp.add_argument("--variant", choices=list(VARIANTS), default="main",
                    help="main warehouse, or holdout (one trap the context pack omits)")
    sp.set_defaults(fn=cmd_bundle)
    sp = sub.add_parser("import-agent-run", help="turn bundle logs into a validated run")
    sp.add_argument("--root", required=True)
    sp.add_argument("--model", required=True)
    sp.add_argument("--out", required=True, help="file name prefix under runs/")
    sp.add_argument("--questions", default="all", help="all | comma list of ids")
    sp.add_argument("--trial", type=int, default=0, help="trial index for repeat runs")
    sp.add_argument("--overwrite", action="store_true")
    sp.set_defaults(fn=cmd_import_agent_run)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    sub.add_parser("lint-memo").set_defaults(fn=cmd_lint_memo)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
