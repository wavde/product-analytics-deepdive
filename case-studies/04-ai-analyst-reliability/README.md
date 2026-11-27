# Case Study 04 — Is Context a Measurable Intervention for AI Analysts?

**Audience:** Data science and analytics leads deciding how much to invest in context for AI analyst agents
**Author:** Senior Data Scientist, Analytics
**Status:** Harness, data and question set complete. **Results pending:** no live model runs have been recorded yet.

## Question

> *Everyone building AI analyst workflows says "give the model more context". Which context actually stops it from giving wrong numbers, and which is ceremony that costs tokens and changes nothing?*

## TL;DR

- **Results pending.** No model has been run through this harness yet, so this memo makes no claim about how any model performs. The results table is generated from saved runs (`results/summary.md`) and is empty until a run is recorded.
- **What is established now** is that the test has teeth. The warehouse reuses case 01's simulated store and adds the mess real event data accumulates. A reasonable first-draft query, the kind an analyst new to the warehouse would write, gets every trap and ambiguous question wrong:

<!-- cited:start -->
- The naive query misses tolerance on 27 of 40 questions [E:naive_wrong_answerable] [E:n_questions], which is 100% of the trap and ambiguous questions [E:naive_wrong_non_control_pct] and none of the controls [E:naive_wrong_controls].
- On 25 of those 27 [E:naive_material_wrong_non_control] [E:n_non_control_answerable] the error is more than one percent of the true value, so it would change a decision, not just fail a reconciliation.
<!-- cited:end -->

- **The design choice that matters:** context is treated as a treatment in an experiment. Every condition gets the same questions, the same SQL tool and the same explicit permission to abstain; only the context changes. That makes "confidently wrong" comparable across conditions instead of an artefact of one prompt being allowed to say "I don't know".

## Why build it this way

I build agent skills for a data science team. The failure that costs the most isn't broken SQL; broken SQL errors out and someone notices. It's a clean-looking number computed under the wrong definition: revenue before refunds, users counted in UTC, an email send counted as activity. Nothing errors, the number is plausible, and it goes into a deck.

So the question I care about isn't "can the model write SQL" but "when does it give a confident wrong answer, and which piece of context prevents that". Context packs grow by accretion: someone gets burned, a paragraph gets added. Nobody measures whether the paragraph works. This case measures it.

Three things here are deliberately different from a prompt-engineering tutorial:

1. **Ground truth is executable.** Every question has a gold query against views that implement the written definitions. Answers are graded numerically, not by a model judging a model.
2. **Trap tags are measured, not asserted.** For each question the gold answer is recomputed with one cleaning rule switched off. If the answer moves outside tolerance, that trap is "live" for that question. Accuracy is then broken down by live trap, which is what lets the memo say *which* context fixes *which* error.
3. **Saved runs are re-executable.** A run file stores the model's words; validation replays them against a fresh warehouse build and recomputes every SQL result, diff and parsed answer. CI never calls a model, but it does prove saved results correspond to this data and this context.

## Design

### The warehouse and its traps

`src/analyst_eval/warehouse.py` builds `data/analyst.db` from case 01's generator (5,000 simulated users, seed 7, unchanged generator) and layers traps on top. Each is documented for the model in `context/traps.md`.

<!-- cited:start -->
| Trap | What it does | Size in this data | Questions it moves |
|---|---|---|---|
| Duplicate retries | Same `event_id` delivered twice | 4.0% extra rows [E:retry_row_pct] | 10 [E:live_duplicates] |
| QA accounts | Internal accounts place weekday test orders | +13.9% orders on weekdays [E:qa_weekday_order_pct] | 21 [E:live_internal_accounts] |
| Messaging events | `email_delivered` / `push_delivered` in the events table | Naive DAU on a Tuesday is 3.0x the real figure [E:t06.naive_over_gold_x] | 12 [E:live_system_events] |
| UTC vs Pacific | Timestamps in UTC, reporting in Los Angeles time (with a DST change) | Shifts every daily, weekly and monthly boundary | 23 [E:live_timezone] |
| Late refunds | Refunds in a separate table, attributed by order date | 792 refunds [E:n_refunds] | 8 [E:live_refunds] |
| Partial final day | Load stops mid-morning Pacific on the last day | Naive "latest day" DAU is 41% low [E:t19.naive_error_pct] | 4 [E:live_partial_period] |
| Cents | Money stored in cents | Largest order reported 100x too big [E:t18.naive_over_gold_x] | 1 [E:live_units] |
| Not instrumented | No sessions, channel, cost or age | A naive sessionisation returns 45,907 "sessions" [E:u04.naive] | 4 [E:live_not_instrumented] |
<!-- cited:end -->

The four data-cleaning traps (duplicates, QA accounts, messaging events, time zone) are measured by single-rule ablation. Refunds, partial periods, units, definitions and uninstrumented data are semantic and tagged by hand in `questions.py`.

### The question set

<!-- cited:start -->
- 40 questions [E:n_questions] in four categories, each with a known answer.
- 7 controls [E:n_control]: no trap moves the answer. They check the harness and confirm context doesn't make simple things worse.
- 19 trap questions [E:n_trap]: unambiguous wording over messy data.
- 8 ambiguous questions [E:n_ambiguous]: wording with more than one reasonable reading ("revenue", "conversion rate", "last week") that `context/definitions.md` resolves.
- 6 unanswerable questions [E:n_unanswerable]: April revenue, paid-search conversion, margin, sessions, a partial day, age. Abstaining is the correct answer.
<!-- cited:end -->

Two controls started life as trap questions: average order value and tablet share. The ablation showed no trap moves either beyond tolerance (QA orders are priced like real ones; duplicates inflate numerator and denominator alike), so they were reclassified rather than kept as traps that don't bite. Ratio metrics being naturally robust to some traps is itself a useful thing to know.

### Conditions

| Condition | System prompt contains | Purpose |
|---|---|---|
| `no_context` | Protocol only; the model explores the database itself | Baseline |
| `schema_only` | + `context/schema.md` (column catalog) | Is a data dictionary enough? |
| `full_context` | + `definitions.md`, `traps.md`, `answer-from-definitions` skill | The full context pack |
| `full_context_reconcile` | Full context, then a forced independent recomputation and data-diff | Does verification beat more context? |
| `schema_definitions` *(optional)* | Schema + definitions only | Ablation: are the traps notes ceremony? |
| `context_no_skill` *(optional)* | Schema + definitions + traps, no skill | Ablation: is the procedural skill ceremony? |

The protocol (identical in every condition) gives the model a read-only DuckDB tool and asks for a final JSON answer with `status` of `answered`, `answered_with_caveat` or `abstained`, the value, the SQL that produced it, assumptions and checks.

### Skills

Three agent skills, written as `SKILL.md` files so they can be dropped into an agent runtime unchanged:

- [`answer-from-definitions`](skills/answer-from-definitions/SKILL.md): pin the question to a written definition before writing SQL, build a base layer that applies every ground rule once, run pre-flight checks, abstain when the spec can't be filled in.
- [`reconcile-results`](skills/reconcile-results/SKILL.md): recompute by a genuinely different route and diff the results; classify any gap as rounding, definitional, bug or unexplained. The harness implements the diff (`reconcile.py`) and injects it in the `full_context_reconcile` condition.
- [`cited-memo`](skills/cited-memo/SKILL.md): every numeric claim cites evidence and the checks it passed. `memo_lint.py` enforces it mechanically. **This README is linted in CI**: every number inside its cited sections must match `results/evidence.json` at the precision written.

### Metrics

| Metric | Definition |
|---|---|
| Accuracy | Within strict tolerance (exact counts, $1, 0.05 points), or abstained on an unanswerable question |
| Materially correct | Accuracy, but also accepting answers within 1% of gold |
| Confidently wrong | Wrong with status `answered`, i.e. no caveat. The error that reaches a decision unchallenged |
| Caveated wrong | Wrong but flagged with `answered_with_caveat` |
| Over-abstained | Abstained on an answerable question |
| Matched naive answer | Wrong answer equal to the naive query's answer: the model fell for the planted trap |
| Cost | Tokens in / out per question, cost per question and **cost per correct answer** at caller-supplied prices |

Differences between conditions are reported with a paired bootstrap 95% CI over questions, because 40 questions is small and the same questions appear in every arm.

## What the traps cost a naive analyst

Deterministic, no model involved: the naive query for each question against the gold answer.

<!-- cited:start -->
| Question | Naive | Gold | Naive error | What went wrong |
|---|---|---|---|---|
| DAU on Tuesday 2025-03-04 | 3,501 [E:t06.naive] | 1,148 [E:t06.gold] | +205% [E:t06.naive_error_pct] | Lifecycle email counted as activity |
| Orders in February | 4,635 [E:t01.naive] | 4,095 [E:t01.gold] | +13.2% [E:t01.naive_error_pct] | Retries, QA orders and UTC month boundaries |
| Net revenue in February | $132,143 [E:t03.naive] | $113,915 [E:t03.gold] | +16.0% [E:t03.naive_error_pct] | Refunds attributed by refund date; retries; QA |
| Refund rate, January orders | 2.31% [E:t05.naive] | 6.49% [E:t05.gold] | −64% [E:t05.naive_error_pct] | Refund-date attribution misses refunds that land later |
| Week-1 retention, cohort of week starting 2025-01-13 | 100% [E:a08.naive] | 85.2% [E:a08.gold] | +17% [E:a08.naive_error_pct] | "Retention" read as ever-returned, emails counted |
| "Conversion rate" in February | 14.2% [E:a02.naive] | 61.4% [E:a02.gold] | −77% [E:a02.naive_error_pct] | Orders per view instead of the team's user-level definition |
| DAU on the latest complete day | 903 [E:t19.naive] | 1,540 [E:t19.gold] | −41% [E:t19.naive_error_pct] | Anchored on a half-loaded day |
| Distinct purchasers, 1-30 March | 3,056 [E:t10.naive] | 3,057 [E:t10.gold] | −0.03% [E:t10.naive_error_pct] | QA accounts and time zone nearly cancel out |
<!-- cited:end -->

The last row is the uncomfortable one for any grading scheme: two real errors that happen to cancel. Strict grading calls it wrong; the materiality lens calls it fine. Both are reported.

## Results

**Results pending.** No live model run has been recorded, so there are no accuracy, confidently-wrong or cost figures yet, and no conclusion about which context is ceremony. `results/summary.md` is generated from validated runs in `runs/` and currently says the same.

When runs exist, this section will report, per condition: accuracy, materially-correct rate, confidently-wrong rate, cost per correct answer, accuracy broken down by live trap, and lift over `no_context` with a 95% CI.

## Predictions, written before any run

Recorded now so the results can't be rationalised afterwards. None of these is a finding.

1. `schema_only` will fix units and most uninstrumented-data abstentions (the catalog says "cents" and lists what exists) but not refunds attribution, the activity definition or the reporting time zone, because those are business rules, not column facts.
2. The definitions file will carry most of the gain on ambiguous questions; the traps file will carry most of the gain on duplicates and partial periods. `schema_definitions` vs `context_no_skill` tests this.
3. The `answer-from-definitions` skill will mainly move errors from confidently wrong to caveated or abstained, rather than raise accuracy.
4. Reconciliation will catch duplicate and join errors (a second route usually disagrees) but not definitional errors (both routes share the misreading), and will roughly double cost per question.
5. No condition will be perfect on the time-zone trap around the DST change.

**Decision rule for "ceremony".** A context component is ceremony if removing it changes neither accuracy nor the confidently-wrong rate by more than the 95% CI of the paired difference, while costing more tokens. A component that only moves the materially-correct rate by less than its CI is reported as "cosmetic" for decision-making.

## Limitations

1. **The context pack documents exactly the traps I planted.** That makes `full_context` an upper bound on what context can do. Real warehouses have traps nobody has written down yet, which is the case for reconciliation over documentation.
2. **Synthetic data and one author.** The traps, definitions and gold queries are mine. A definition I wrote ambiguously would show up as model error. The pandas cross-check in the tests reconciles a sample of gold answers by an independent route, but not all of them.
3. **Small n.** 40 questions gives wide intervals. The harness supports repeated trials; with one model and one trial, only large effects will be distinguishable from noise.
4. **Status is a proxy for confidence.** "Confidently wrong" relies on the model's own choice of `answered` vs `answered_with_caveat`. Models calibrate that differently.
5. **Scalar answers only.** The set grades numbers, not charts, narratives or the quality of a written insight. The cited-memo skill is checked for traceability, not for being a good memo.
6. **Cost estimates before a run are rough.** `cli.py plan` uses a characters-per-token heuristic; real costs come from the provider's token counts in the run file.

## How to run

From the repo root, with the environment from the main README:

```bash
cd case-studies/04-ai-analyst-reliability
python src/cli.py build        # warehouse, answer key and evidence (deterministic, ~5s)
python src/cli.py plan --price-in <usd_per_mtok> --price-out <usd_per_mtok>   # token + cost estimate
python src/cli.py lint-memo    # check this README against results/evidence.json
```

A live run calls a paid API and needs a key in the environment. It refuses to start without prices and a budget cap, and stops when the cap is reached:

```bash
export ANTHROPIC_API_KEY=...   # or OPENAI_API_KEY with --provider openai-compatible [--base-url ...]
python src/cli.py run --provider anthropic --model <model-id> \
    --price-in <usd_per_mtok> --price-out <usd_per_mtok> --max-cost-usd 20
python src/cli.py validate     # replay saved runs offline against a fresh build
python src/cli.py report       # regenerate results/summary.{json,md}
```

Use `--conditions all` to include the two ablations and `--trials N` for repeated runs.

## Files

| Path | What it is |
|---|---|
| `context/` | The context pack: `schema.md`, `definitions.md`, `traps.md` |
| `skills/` | The three agent skills |
| `src/analyst_eval/warehouse.py` | Builds the trap-laden warehouse from case 01's generator |
| `src/analyst_eval/gold.py`, `questions.py`, `answer_key.py` | Definitions as views, the 40 questions, the answer key with measured traps |
| `src/analyst_eval/agent.py`, `conditions.py`, `runners.py` | Agent loop, the conditions, pluggable model runners (Anthropic, OpenAI-compatible, replay) |
| `src/analyst_eval/reconcile.py`, `grading.py`, `runs.py`, `report.py` | Data-diff, grading, run persistence and replay validation, results tables |
| `src/analyst_eval/evidence.py`, `memo_lint.py` | Evidence for this memo and the linter that checks it |
| `questions/answer_key.json` | Gold and naive answers and live traps per question (regenerated and compared in CI) |
| `results/` | `evidence.json` (memo evidence) and `summary.md` (model results, pending) |
| `runs/` | Saved model runs (none yet) |
