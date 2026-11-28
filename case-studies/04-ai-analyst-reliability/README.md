# Case Study 04 — Is Context a Measurable Intervention for AI Analysts?

**Audience:** Data science and analytics leads deciding how much to invest in context for AI analyst agents
**Author:** Senior Data Scientist, Analytics
**Status:** Complete for one model. 160 graded answers from `claude-opus-5.5` (40 questions × 4 conditions, one trial), run as GitHub Copilot sub-agents in blind folders. Every logged query has been re-run against a fresh build to validate the results.

## Question

> *Everyone building AI analyst workflows says "give the model more context". Which context actually stops it from giving wrong numbers, and which is ceremony that costs tokens and changes nothing?*

## TL;DR

<!-- cited:start -->
- **Written business conventions are what work.** With the full context pack the model answered 40 of 40 correctly [E:run.claude-opus-5.5.t0.full_context.correct] [E:run.claude-opus-5.5.t0.full_context.n]. With no context it got 13 [E:run.claude-opus-5.5.t0.no_context.correct], and with the schema catalog alone 15 [E:run.claude-opus-5.5.t0.schema_only.correct].
- **The model wasn't naive without context.** By exploring the data it found the duplicate events, QA accounts and messaging rows on its own. None of its wrong answers equalled the naive first-draft query's answer [E:run.claude-opus-5.5.t0.no_context.matched_naive].
- **What it couldn't find was convention.** 19 of its 27 misses [E:run.claude-opus-5.5.t0.no_context.wrong_tz_only] [E:run.claude-opus-5.5.t0.no_context.wrong] are exactly the right answer computed in UTC instead of the business's Pacific time. The rest are definitional: gross vs net revenue, refund rate by count vs by dollars, retention window.
- **It flagged its uncertainty.** 26 of the 27 misses carried a caveat [E:run.claude-opus-5.5.t0.no_context.caveated_wrong] [E:run.claude-opus-5.5.t0.no_context.wrong]. Only 1 was confidently wrong [E:run.claude-opus-5.5.t0.no_context.confidently_wrong].
- **Reconciliation was ceremony on this set.** There were 34 independent recomputations [E:run.claude-opus-5.5.t0.full_context_reconcile.reconciled]. All of them matched [E:run.claude-opus-5.5.t0.full_context_reconcile.reconcile_match], none changed an answer [E:run.claude-opus-5.5.t0.full_context_reconcile.reconcile_changed], and median time per question rose from 12.5 to 24.2 seconds [E:run.claude-opus-5.5.t0.full_context.median_seconds] [E:run.claude-opus-5.5.t0.full_context_reconcile.median_seconds].
<!-- cited:end -->

**Practitioner takeaway:** write down what the data can't tell a model: reporting time zone, how refunds are attributed, what "active", "revenue" and "retention" mean, and when a period is complete. Don't spend context on traps a capable model finds by profiling the data. Keep reconciliation for weaker models or warehouses with real join bugs; here it found nothing to fix.

The test has teeth. A reasonable first-draft query, the kind an analyst new to this warehouse would write, gets every trap and ambiguous question wrong:

<!-- cited:start -->
- The naive query misses tolerance on 27 of 40 questions [E:naive_wrong_answerable] [E:n_questions]. That is 100% of the trap and ambiguous questions [E:naive_wrong_non_control_pct] and none of the controls [E:naive_wrong_controls].
- On 25 of those 27 [E:naive_material_wrong_non_control] [E:n_non_control_answerable], the error is more than one percent of the true value, so it would change a decision, not just fail a reconciliation.
<!-- cited:end -->

**The design choice that matters:** context is treated as a treatment in an experiment. Every condition gets the same questions, the same SQL tool and the same explicit permission to abstain; only the context changes. That makes "confidently wrong" comparable across conditions, rather than a side effect of only one prompt being allowed to say "I don't know".

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

### How the run was executed

No API key was available, so the experiment ran inside GitHub Copilot.

- **The analysts:** each answer came from a fresh `claude-opus-5.5` sub-agent working on one question in one condition.
- **The blind folder:** each agent worked in a folder outside the repo containing only:
  - the raw database
  - that condition's `AGENT.md`, which holds the same protocol and context the API harness would send as a system prompt
  - `tool.py`, its only way to query the data and submit an answer
- **What's excluded:** there was no answer key, gold SQL or grading code in the folder.
- **The record:** `tool.py` logs every query, result and answer itself, so the record doesn't depend on what the agent reported. `cli.py import-agent-run` turns those logs into `runs/full_github-copilot_claude-opus-5.5.jsonl`. Validation re-runs every logged query against a freshly built warehouse; CI does the same.

### Scorecard

<!-- cited:start -->
| Condition | Correct | Within one percent | Confidently wrong | Wrong with caveat | Queries per question | Median seconds |
|---|---|---|---|---|---|---|
| no_context | 13 [E:run.claude-opus-5.5.t0.no_context.correct] | 72.5% [E:run.claude-opus-5.5.t0.no_context.material_pct] | 1 [E:run.claude-opus-5.5.t0.no_context.confidently_wrong] | 26 [E:run.claude-opus-5.5.t0.no_context.caveated_wrong] | 3.8 [E:run.claude-opus-5.5.t0.no_context.sql_per_q] | 30.1 [E:run.claude-opus-5.5.t0.no_context.median_seconds] |
| schema_only | 15 [E:run.claude-opus-5.5.t0.schema_only.correct] | 80% [E:run.claude-opus-5.5.t0.schema_only.material_pct] | 1 [E:run.claude-opus-5.5.t0.schema_only.confidently_wrong] | 24 [E:run.claude-opus-5.5.t0.schema_only.caveated_wrong] | 2.5 [E:run.claude-opus-5.5.t0.schema_only.sql_per_q] | 16.3 [E:run.claude-opus-5.5.t0.schema_only.median_seconds] |
| full_context | 40 [E:run.claude-opus-5.5.t0.full_context.correct] | 100% [E:run.claude-opus-5.5.t0.full_context.material_pct] | 0 [E:run.claude-opus-5.5.t0.full_context.confidently_wrong] | 0 [E:run.claude-opus-5.5.t0.full_context.caveated_wrong] | 2.0 [E:run.claude-opus-5.5.t0.full_context.sql_per_q] | 12.5 [E:run.claude-opus-5.5.t0.full_context.median_seconds] |
| full_context_reconcile | 40 [E:run.claude-opus-5.5.t0.full_context_reconcile.correct] | 100% [E:run.claude-opus-5.5.t0.full_context_reconcile.material_pct] | 0 [E:run.claude-opus-5.5.t0.full_context_reconcile.confidently_wrong] | 0 [E:run.claude-opus-5.5.t0.full_context_reconcile.caveated_wrong] | 1.9 [E:run.claude-opus-5.5.t0.full_context_reconcile.sql_per_q] | 24.2 [E:run.claude-opus-5.5.t0.full_context_reconcile.median_seconds] |
<!-- cited:end -->

Each condition has 40 answers. Accuracy by live trap and the paired-bootstrap lift over `no_context` are in [`results/summary.md`](results/summary.md), which is generated from the validated run. Tokens and dollar cost can't be measured through Copilot, so the cost columns there read `n/a`. Queries per question and wall time stand in for cost.

### What the errors were

<!-- cited:start -->
- **Time zone dominates.** Without context, 19 of 27 misses [E:run.claude-opus-5.5.t0.no_context.wrong_tz_only] [E:run.claude-opus-5.5.t0.no_context.wrong] match the gold answer recomputed with only the Pacific-time rule switched off. With the schema alone it is 21 of 25 [E:run.claude-opus-5.5.t0.schema_only.wrong_tz_only] [E:run.claude-opus-5.5.t0.schema_only.wrong]. Every agent saw UTC-looking timestamps, and several said in their caveat that the reporting zone was unknown. None could get it right without being told.
- **Most of those misses are small.** Only 11 no-context answers [E:run.claude-opus-5.5.t0.no_context.material_wrong] and 8 schema-only answers [E:run.claude-opus-5.5.t0.schema_only.material_wrong] were more than one percent off. The big ones were definitional: "revenue" answered gross, "refund rate" answered by order count, "ARPU" before refunds, and daily counts where a third of a day moves.
- **The discoverable traps weren't a problem.** No answer in any condition equalled the naive query's answer [E:run.claude-opus-5.5.t0.no_context.matched_naive] [E:run.claude-opus-5.5.t0.schema_only.matched_naive]. With no documentation, the agents found duplicate event ids, the internal-account flag, messaging events and the load watermark by profiling the data.
<!-- cited:end -->

### Which context earned its place

| Component | Verdict for this model | Evidence |
|---|---|---|
| Metric definitions + reporting conventions (`definitions.md`) | **Essential.** The only fix for time zone, refund attribution and ambiguous terms. | Every miss in the two lighter conditions is a convention the data can't reveal. Both full-context conditions scored 40/40. |
| Schema catalog (`schema.md`) | **Marginal.** It reduced exploration (fewer queries, shorter runs) and turned one sessionisation into an abstention, but barely moved accuracy. | 15 vs 13 correct. The lift CI includes zero (`results/summary.md`). |
| Known-traps notes (`traps.md`) | **Probably ceremony for the discoverable traps** (duplicates, QA accounts, messaging events), since agents without it found them anyway. **Untested in isolation**, because the ablations that split it out weren't run. | Matched-naive count is zero without any traps notes. |
| `answer-from-definitions` skill | **Untested in isolation**, for the same reason. | — |
| Reconcile step | **Ceremony on this set.** It never disagreed and never changed an answer, and it roughly doubled median time. Its value can't be shown when full context leaves nothing to catch. | See the TL;DR figures. |

### How the predictions held up

1. *Schema fixes units and uninstrumented abstentions but not business rules.* **Mostly right.** Units were never a problem even with no context, and the schema did produce the abstention on sessions. Business-rule errors were untouched.
2. *Definitions drive the gain on ambiguous questions; the traps file drives duplicates and partial periods.* **Half right.** Definitions did carry the ambiguous questions, but the agents handled duplicates with no traps file at all. The ablations needed to settle this weren't run.
3. *The skill mainly turns confident errors into caveated ones.* **Wrong premise.** Without context the agents were already caveating almost every miss. Context raised accuracy instead of changing confidence.
4. *Reconciliation catches duplicate and join errors, not definitional ones, at about double the cost.* **Untestable here.** There were no errors left to catch. The time cost was about double, as predicted.
5. *No condition is perfect on the DST time-zone trap.* **Wrong.** Given the rule in writing, every full-context answer handled it.

The surprise is the second-order point: a strong model is a better data profiler than I assumed, and a worse mind-reader. Context work should go into conventions, not data quirks.

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
6. **One model, one trial, run through Copilot.** The model was pinned, but sampling settings like temperature couldn't be. Each agent also had Copilot's own system prompt and tools on top of the protocol. A second trial, or a different model, could move individual answers. Weaker models may well need the traps notes and reconciliation that looked like ceremony here.
7. **Isolation was by instruction, not enforcement.** The agents had general file access and were told to stay in their folder. Logs and a post-run audit found no stray files in the bundles or the repo. One agent ran its first command from the repo folder, created and deleted an empty work folder, then redid its work in the right place. File *reads* outside the folder can't be audited. The bundles sat outside the repo and contained no answers, so the main exposure was reading another condition's context folder. Nothing in the logs or the answers suggests that happened.
8. **No token or dollar cost.** Copilot doesn't expose per-call token counts to the harness, so cost is shown as queries and wall time. The API path in `runners.py` records real tokens and cost when a key is available.

## How to run

From the repo root, with the environment from the main README:

```bash
cd case-studies/04-ai-analyst-reliability
python src/cli.py build        # warehouse, answer key and evidence (deterministic, ~5s)
python src/cli.py plan --price-in <usd_per_mtok> --price-out <usd_per_mtok>   # token + cost estimate
python src/cli.py lint-memo    # check this README against results/evidence.json
```

**Agent route (no API key):** build blind folders outside the repo, have one agent per condition × question follow that folder's `AGENT.md`, then import the tool logs:

```bash
python src/cli.py bundle --root <folder outside the repo> --python <python with duckdb>
# run one agent per (condition, question): "Read <root>/<condition>/AGENT.md and follow it.
#   Question id: <id>. Question: <text>."
python src/cli.py import-agent-run --root <same folder> --model <model id> --out full
python src/cli.py report
```

**API route:** a live run calls a paid API and needs a key in the environment. It refuses to start without prices and a budget cap, and stops when the cap is reached:

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
| `src/analyst_eval/agent_runs.py`, `bundle_tool.py` | Blind bundles for Copilot-agent runs, the logged analyst tool, log import and validation |
| `src/analyst_eval/reconcile.py`, `grading.py`, `runs.py`, `report.py` | Data-diff, grading, run persistence and replay validation, results tables |
| `src/analyst_eval/evidence.py`, `memo_lint.py` | Evidence for this memo and the linter that checks it |
| `questions/answer_key.json` | Gold and naive answers and live traps per question (regenerated and compared in CI) |
| `results/` | `evidence.json` (memo evidence) and `summary.md` (per-condition results) |
| `runs/` | Saved, validated model runs |
