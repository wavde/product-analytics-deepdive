# Case Study 04 — Is Context a Measurable Intervention for AI Analysts?

**Audience:** Data science and analytics leads deciding how much to invest in context for AI analyst agents
**Author:** Senior Data Scientist, Analytics
**Status:** Complete. 860 graded answers, run as GitHub Copilot sub-agents in blind folders:
- `claude-opus-5.5` and `claude-haiku-5.5`: the four core conditions twice each (two independent trials), plus the two ablations once.
- Both models: a holdout of 10 questions on a warehouse with one trap the context pack never mentions, with predictions committed before the run.

Every logged query has been re-run against a fresh build to validate the results.

## Question

> *Everyone building AI analyst workflows says "give the model more context". Which context actually stops it from giving wrong numbers, and which is ceremony that costs tokens and changes nothing?*

## TL;DR

<!-- cited:start -->
- **Written business conventions are what work.** With the full context pack `claude-opus-5.5` answered 40 of 40 correctly [E:run.claude-opus-5.5.t0.full_context.correct] [E:run.claude-opus-5.5.t0.full_context.n]. With no context it got 13 [E:run.claude-opus-5.5.t0.no_context.correct], and with the schema catalog alone 15 [E:run.claude-opus-5.5.t0.schema_only.correct].
- **It reproduced.** A second, independent trial scored 14 with no context [E:run.claude-opus-5.5.t1.no_context.correct], 13 with schema only [E:run.claude-opus-5.5.t1.schema_only.correct] and 40 with full context [E:run.claude-opus-5.5.t1.full_context.correct]. Without context, 37 of 40 questions [E:run.claude-opus-5.5.no_context.same_outcome] [E:run.claude-opus-5.5.no_context.n_repeated] got the same graded outcome both times.
- **The definitions file did all the work, for both models.** Schema plus definitions alone scored 40 of 40 for Opus [E:run.claude-opus-5.5.t0.schema_definitions.correct] and for Haiku [E:run.claude-haiku-5.5.t0.schema_definitions.correct]. The traps notes and the procedural skill added nothing measurable on top.
- **A weaker model needed the same pack and was rescued by it.** `claude-haiku-5.5` scored 14 then 13 with no context [E:run.claude-haiku-5.5.t0.no_context.correct] [E:run.claude-haiku-5.5.t1.no_context.correct] and 40 in both trials with full context [E:run.claude-haiku-5.5.t0.full_context.correct] [E:run.claude-haiku-5.5.t1.full_context.correct]. Unlike Opus, it fell for planted traps: 6 of its misses equalled the naive query's answer [E:run.claude-haiku-5.5.t0.no_context.matched_naive], against none for Opus [E:run.claude-opus-5.5.t0.no_context.matched_naive].
- **The pack held on a trap it never mentions.** On a holdout warehouse with re-submitted purchases (new event id, same order), both models scored 10 of 10 with full context [E:run.claude-opus-5.5.holdout.t0.full_context.correct] [E:run.claude-haiku-5.5.holdout.t0.full_context.correct] and 0 without it [E:run.claude-opus-5.5.holdout.t0.no_context.correct] [E:run.claude-haiku-5.5.holdout.t0.no_context.correct]. That refuted my preregistered prediction. The reason matters: the written definition of an order (one per `order_id`) covered the trap without naming it.
- **Opus wasn't naive without context; it just couldn't read minds.** 19 of its 27 misses [E:run.claude-opus-5.5.t0.no_context.wrong_tz_only] [E:run.claude-opus-5.5.t0.no_context.wrong] are exactly the right answer computed in UTC instead of the business's Pacific time. 26 of the 27 carried a caveat [E:run.claude-opus-5.5.t0.no_context.caveated_wrong] [E:run.claude-opus-5.5.t0.no_context.wrong].
- **Reconciliation was ceremony on this set, for both models.** Four runs each forced 34 independent recomputations [E:run.claude-opus-5.5.t0.full_context_reconcile.reconciled] [E:run.claude-opus-5.5.t1.full_context_reconcile.reconciled] [E:run.claude-haiku-5.5.t0.full_context_reconcile.reconciled] [E:run.claude-haiku-5.5.t1.full_context_reconcile.reconciled], and none changed an answer [E:run.claude-opus-5.5.t0.full_context_reconcile.reconcile_changed] [E:run.claude-opus-5.5.t1.full_context_reconcile.reconcile_changed] [E:run.claude-haiku-5.5.t0.full_context_reconcile.reconcile_changed] [E:run.claude-haiku-5.5.t1.full_context_reconcile.reconcile_changed]; nor did it change any on the holdout [E:run.claude-opus-5.5.holdout.t0.full_context_reconcile.reconcile_changed] [E:run.claude-haiku-5.5.holdout.t0.full_context_reconcile.reconcile_changed]. It roughly doubled median time: 12.5 to 24.2 seconds for Opus [E:run.claude-opus-5.5.t0.full_context.median_seconds] [E:run.claude-opus-5.5.t0.full_context_reconcile.median_seconds], 21.7 to 49.6 for Haiku [E:run.claude-haiku-5.5.t0.full_context.median_seconds] [E:run.claude-haiku-5.5.t0.full_context_reconcile.median_seconds].
<!-- cited:end -->

**Practitioner takeaway:** write down what the data can't tell a model: reporting time zone, how refunds are attributed, what "active", "revenue" and "retention" mean, when a period is complete, the grain of each entity (an order is one `order_id`), and the one-line ground rules (exclude internal accounts, one row per event id, user-initiated events only). For both models that was the whole job; a page of trap essays and a procedural skill added nothing. The weaker model *did* trip over the data quirks without context, and the same page fixed it. Definitions written at the right grain also caught a quirk nobody had documented. Keep reconciliation for warehouses with real join bugs; here it found nothing to fix for either model.

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
| `schema_definitions` | Schema + definitions only | Ablation: are the traps notes and skill ceremony? (run for Opus) |
| `context_no_skill` | Schema + definitions + traps, no skill | Ablation: is the procedural skill ceremony? (run for Opus) |

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

- **The analysts:** each answer came from a fresh sub-agent of the model under test, working on one question in one condition.
- **The blind folder:** each agent worked in a folder outside the repo containing only:
  - the raw database
  - that condition's `AGENT.md`, which holds the same protocol and context the API harness would send as a system prompt
  - `tool.py`, its only way to query the data and submit an answer
- **What's excluded:** there was no answer key, gold SQL or grading code in the folder.
- **The record:** `tool.py` logs every query, result and answer itself, so the record doesn't depend on what the agent reported. `cli.py import-agent-run` turns those logs into the run files in `runs/` (listed in [`runs/README.md`](runs/README.md)). Validation re-runs every logged query against a freshly built warehouse; CI does the same.
- **Second trials** used fresh bundles and fresh agents, with nothing carried over from the first. The Haiku runs used bundles identical to Opus's; only the model differed.
- **One harness fix after the runs:** the importer flagged a reconciliation as having "changed" the answer when the same number came back with different trailing float digits (`38.13701372614664` vs `38.137013726146634`). Change detection now uses a relative tolerance of 1e-9; the affected run was re-imported from its raw logs, not edited.

### Scorecard: `claude-opus-5.5`, first trial

<!-- cited:start -->
| Condition | Correct | Within one percent | Confidently wrong | Wrong with caveat | Queries per question | Median seconds |
|---|---|---|---|---|---|---|
| no_context | 13 [E:run.claude-opus-5.5.t0.no_context.correct] | 72.5% [E:run.claude-opus-5.5.t0.no_context.material_pct] | 1 [E:run.claude-opus-5.5.t0.no_context.confidently_wrong] | 26 [E:run.claude-opus-5.5.t0.no_context.caveated_wrong] | 3.8 [E:run.claude-opus-5.5.t0.no_context.sql_per_q] | 30.1 [E:run.claude-opus-5.5.t0.no_context.median_seconds] |
| schema_only | 15 [E:run.claude-opus-5.5.t0.schema_only.correct] | 80% [E:run.claude-opus-5.5.t0.schema_only.material_pct] | 1 [E:run.claude-opus-5.5.t0.schema_only.confidently_wrong] | 24 [E:run.claude-opus-5.5.t0.schema_only.caveated_wrong] | 2.5 [E:run.claude-opus-5.5.t0.schema_only.sql_per_q] | 16.3 [E:run.claude-opus-5.5.t0.schema_only.median_seconds] |
| full_context | 40 [E:run.claude-opus-5.5.t0.full_context.correct] | 100% [E:run.claude-opus-5.5.t0.full_context.material_pct] | 0 [E:run.claude-opus-5.5.t0.full_context.confidently_wrong] | 0 [E:run.claude-opus-5.5.t0.full_context.caveated_wrong] | 2.0 [E:run.claude-opus-5.5.t0.full_context.sql_per_q] | 12.5 [E:run.claude-opus-5.5.t0.full_context.median_seconds] |
| full_context_reconcile | 40 [E:run.claude-opus-5.5.t0.full_context_reconcile.correct] | 100% [E:run.claude-opus-5.5.t0.full_context_reconcile.material_pct] | 0 [E:run.claude-opus-5.5.t0.full_context_reconcile.confidently_wrong] | 0 [E:run.claude-opus-5.5.t0.full_context_reconcile.caveated_wrong] | 1.9 [E:run.claude-opus-5.5.t0.full_context_reconcile.sql_per_q] | 24.2 [E:run.claude-opus-5.5.t0.full_context_reconcile.median_seconds] |
<!-- cited:end -->

Each condition has 40 answers. Accuracy by live trap and the paired-bootstrap lift over `no_context` are in [`results/summary.md`](results/summary.md), which is generated from the validated run. Tokens and dollar cost can't be measured through Copilot, so the cost columns there read `n/a`. Queries per question and wall time stand in for cost.

### What the errors were (Opus, first trial)

<!-- cited:start -->
- **Time zone dominates.** Without context, 19 of 27 misses [E:run.claude-opus-5.5.t0.no_context.wrong_tz_only] [E:run.claude-opus-5.5.t0.no_context.wrong] match the gold answer recomputed with only the Pacific-time rule switched off. With the schema alone it is 21 of 25 [E:run.claude-opus-5.5.t0.schema_only.wrong_tz_only] [E:run.claude-opus-5.5.t0.schema_only.wrong]. Every agent saw UTC-looking timestamps, and several said in their caveat that the reporting zone was unknown. None could get it right without being told.
- **Most of those misses are small.** Only 11 no-context answers [E:run.claude-opus-5.5.t0.no_context.material_wrong] and 8 schema-only answers [E:run.claude-opus-5.5.t0.schema_only.material_wrong] were more than one percent off. The big ones were definitional: "revenue" answered gross, "refund rate" answered by order count, "ARPU" before refunds, and daily counts where a third of a day moves.
- **The discoverable traps weren't a problem for Opus.** None of its answers in either lighter condition equalled the naive query's answer [E:run.claude-opus-5.5.t0.no_context.matched_naive] [E:run.claude-opus-5.5.t0.schema_only.matched_naive]. With no documentation, the agents found duplicate event ids, the internal-account flag, messaging events and the load watermark by profiling the data.
<!-- cited:end -->

### Second trial: is it stable?

The four core conditions were rerun for `claude-opus-5.5` with fresh bundles and fresh agents.

<!-- cited:start -->
| Condition | Correct, first trial | Correct, second trial | Same graded outcome in both |
|---|---|---|---|
| no_context | 13 [E:run.claude-opus-5.5.t0.no_context.correct] | 14 [E:run.claude-opus-5.5.t1.no_context.correct] | 37 of 40 [E:run.claude-opus-5.5.no_context.same_outcome] [E:run.claude-opus-5.5.no_context.n_repeated] |
| schema_only | 15 [E:run.claude-opus-5.5.t0.schema_only.correct] | 13 [E:run.claude-opus-5.5.t1.schema_only.correct] | 38 of 40 [E:run.claude-opus-5.5.schema_only.same_outcome] [E:run.claude-opus-5.5.schema_only.n_repeated] |
| full_context | 40 [E:run.claude-opus-5.5.t0.full_context.correct] | 40 [E:run.claude-opus-5.5.t1.full_context.correct] | 40 of 40 [E:run.claude-opus-5.5.full_context.same_outcome] [E:run.claude-opus-5.5.full_context.n_repeated] |
| full_context_reconcile | 40 [E:run.claude-opus-5.5.t0.full_context_reconcile.correct] | 40 [E:run.claude-opus-5.5.t1.full_context_reconcile.correct] | 40 of 40 [E:run.claude-opus-5.5.full_context_reconcile.same_outcome] [E:run.claude-opus-5.5.full_context_reconcile.n_repeated] |

- **The headline held.** In the second trial the time zone again explained 20 of 26 no-context misses [E:run.claude-opus-5.5.t1.no_context.wrong_tz_only] [E:run.claude-opus-5.5.t1.no_context.wrong], and the second reconcile run changed no answers either [E:run.claude-opus-5.5.t1.full_context_reconcile.reconcile_changed].
<!-- cited:end -->

The five questions that changed outcome are informative. All of them came from the lighter conditions:

- **Sessions (`u04`).** The sessions question was abstained on under `schema_only` in the first trial and under `no_context` in the second; in the other cell each time, the agent built a 30-minute sessionisation instead. So my first-trial reading that the schema catalog "produces the abstention" was noise.
- **ARPU (`a07`).** Correct under `schema_only` in one trial, gross-before-refunds in the other.
- **Retention (`a08`).** Caveated and wrong under `no_context` in one trial, abstained (over-cautiously) in the other.
- **Week-1 activity (`t16`).** The same wrong value both times, once caveated and once not. The confident/caveated label is itself noisy, which matters for any metric built on it, including "confidently wrong".

With full context there was nothing to vary: 80 of 80 answers correct in each full-context condition across the two trials.

### Ablations: which part of the pack did the work?

Run once per model.

<!-- cited:start -->
| Condition | What's in context | Opus correct | Opus queries per question | Haiku correct | Haiku queries per question |
|---|---|---|---|---|---|
| full_context (first trial) | schema, definitions, traps, skill | 40 [E:run.claude-opus-5.5.t0.full_context.correct] | 2.0 [E:run.claude-opus-5.5.t0.full_context.sql_per_q] | 40 [E:run.claude-haiku-5.5.t0.full_context.correct] | 2.1 [E:run.claude-haiku-5.5.t0.full_context.sql_per_q] |
| context_no_skill | schema, definitions, traps | 40 [E:run.claude-opus-5.5.t0.context_no_skill.correct] | 1.15 [E:run.claude-opus-5.5.t0.context_no_skill.sql_per_q] | 40 [E:run.claude-haiku-5.5.t0.context_no_skill.correct] | 1.525 [E:run.claude-haiku-5.5.t0.context_no_skill.sql_per_q] |
| schema_definitions | schema, definitions | 40 [E:run.claude-opus-5.5.t0.schema_definitions.correct] | 1.65 [E:run.claude-opus-5.5.t0.schema_definitions.sql_per_q] | 40 [E:run.claude-haiku-5.5.t0.schema_definitions.correct] | 1.825 [E:run.claude-haiku-5.5.t0.schema_definitions.sql_per_q] |
<!-- cited:end -->

- **The traps notes and the skill added nothing measurable for either model.** Every arm that had the definitions file scored 40 of 40, including Haiku, which fell for the traps without context. Without the skill both models ran fewer queries, not more; the skill asks for pre-flight checks, which is the likely reason.
- **Read this carefully.** `definitions.md` isn't only metric definitions. It states the ground rules that implement each trap fix in one line apiece: exclude internal accounts, one row per `event_id`, only user-initiated events count as activity, report in Pacific time, attribute refunds to the order date, report complete periods only. So the ablation shows that the trap *descriptions* in `traps.md` and the procedural skill were redundant once those rules were written down. It does not show that the fixes were unnecessary; the arms without the rules are `no_context` and `schema_only`, which is where every error was.

### A weaker model: `claude-haiku-5.5`

Same bundles, same questions. First trial:

<!-- cited:start -->
| Condition | Correct | Within one percent | Confidently wrong | Wrong with caveat | Matched naive answer | Queries per question | Median seconds |
|---|---|---|---|---|---|---|---|
| no_context | 14 [E:run.claude-haiku-5.5.t0.no_context.correct] | 52.5% [E:run.claude-haiku-5.5.t0.no_context.material_pct] | 3 [E:run.claude-haiku-5.5.t0.no_context.confidently_wrong] | 23 [E:run.claude-haiku-5.5.t0.no_context.caveated_wrong] | 6 [E:run.claude-haiku-5.5.t0.no_context.matched_naive] | 4.0 [E:run.claude-haiku-5.5.t0.no_context.sql_per_q] | 60.5 [E:run.claude-haiku-5.5.t0.no_context.median_seconds] |
| schema_only | 13 [E:run.claude-haiku-5.5.t0.schema_only.correct] | 57.5% [E:run.claude-haiku-5.5.t0.schema_only.material_pct] | 1 [E:run.claude-haiku-5.5.t0.schema_only.confidently_wrong] | 26 [E:run.claude-haiku-5.5.t0.schema_only.caveated_wrong] | 2 [E:run.claude-haiku-5.5.t0.schema_only.matched_naive] | 2.3 [E:run.claude-haiku-5.5.t0.schema_only.sql_per_q] | 27.5 [E:run.claude-haiku-5.5.t0.schema_only.median_seconds] |
| full_context | 40 [E:run.claude-haiku-5.5.t0.full_context.correct] | 100% [E:run.claude-haiku-5.5.t0.full_context.material_pct] | 0 [E:run.claude-haiku-5.5.t0.full_context.confidently_wrong] | 0 [E:run.claude-haiku-5.5.t0.full_context.caveated_wrong] | 0 [E:run.claude-haiku-5.5.t0.full_context.matched_naive] | 2.1 [E:run.claude-haiku-5.5.t0.full_context.sql_per_q] | 21.7 [E:run.claude-haiku-5.5.t0.full_context.median_seconds] |
| full_context_reconcile | 40 [E:run.claude-haiku-5.5.t0.full_context_reconcile.correct] | 100% [E:run.claude-haiku-5.5.t0.full_context_reconcile.material_pct] | 0 [E:run.claude-haiku-5.5.t0.full_context_reconcile.confidently_wrong] | 0 [E:run.claude-haiku-5.5.t0.full_context_reconcile.caveated_wrong] | 0 [E:run.claude-haiku-5.5.t0.full_context_reconcile.matched_naive] | 2.0 [E:run.claude-haiku-5.5.t0.full_context_reconcile.sql_per_q] | 49.6 [E:run.claude-haiku-5.5.t0.full_context_reconcile.median_seconds] |

- **Same score, different failure.** Without context Haiku matched Opus on the headline count, but only 6 of its 26 misses [E:run.claude-haiku-5.5.t0.no_context.wrong_tz_only] [E:run.claude-haiku-5.5.t0.no_context.wrong] were the time zone alone, against 19 of 27 for Opus [E:run.claude-opus-5.5.t0.no_context.wrong_tz_only] [E:run.claude-opus-5.5.t0.no_context.wrong].
- **It missed the discoverable traps.** 8 no-context misses [E:run.claude-haiku-5.5.t0.no_context.wrong_kept_internal] are explained only by keeping the internal QA accounts in, against 1 for Opus [E:run.claude-opus-5.5.t0.no_context.wrong_kept_internal]. It counted email and push deliveries as daily activity, reporting the naive 3,501 DAU [E:t06.naive] where the answer is 1,148 [E:t06.gold].
- **The errors are still the kind a written rule fixes.** 20 of its 26 no-context misses [E:run.claude-haiku-5.5.t0.no_context.wrong_cleaning] [E:run.claude-haiku-5.5.t0.no_context.wrong] equal the gold answer with some combination of the four data-cleaning rules switched off. The rest are definitional.
- **Its errors were bigger.** 19 no-context answers [E:run.claude-haiku-5.5.t0.no_context.material_wrong] were more than one percent off, against 11 for Opus [E:run.claude-opus-5.5.t0.no_context.material_wrong]. Haiku still caveated most misses (23 of 26 [E:run.claude-haiku-5.5.t0.no_context.caveated_wrong] [E:run.claude-haiku-5.5.t0.no_context.wrong]).
<!-- cited:end -->

It also answered the half-loaded last day's DAU with a caveat in both lighter conditions, where Opus abstained. With the full pack, every Haiku answer was correct, including abstaining on that day.

**Second trial.** Fresh bundles and fresh agents again.

<!-- cited:start -->
| Condition | Correct, first trial | Correct, second trial | Same graded outcome in both |
|---|---|---|---|
| no_context | 14 [E:run.claude-haiku-5.5.t0.no_context.correct] | 13 [E:run.claude-haiku-5.5.t1.no_context.correct] | 32 of 40 [E:run.claude-haiku-5.5.no_context.same_outcome] [E:run.claude-haiku-5.5.no_context.n_repeated] |
| schema_only | 13 [E:run.claude-haiku-5.5.t0.schema_only.correct] | 15 [E:run.claude-haiku-5.5.t1.schema_only.correct] | 35 of 40 [E:run.claude-haiku-5.5.schema_only.same_outcome] [E:run.claude-haiku-5.5.schema_only.n_repeated] |
| full_context | 40 [E:run.claude-haiku-5.5.t0.full_context.correct] | 40 [E:run.claude-haiku-5.5.t1.full_context.correct] | 40 of 40 [E:run.claude-haiku-5.5.full_context.same_outcome] [E:run.claude-haiku-5.5.full_context.n_repeated] |
| full_context_reconcile | 40 [E:run.claude-haiku-5.5.t0.full_context_reconcile.correct] | 40 [E:run.claude-haiku-5.5.t1.full_context_reconcile.correct] | 40 of 40 [E:run.claude-haiku-5.5.full_context_reconcile.same_outcome] [E:run.claude-haiku-5.5.full_context_reconcile.n_repeated] |

- **The failure pattern reproduced.** Without context, 7 misses again equalled the naive answer [E:run.claude-haiku-5.5.t1.no_context.matched_naive], 8 again were explained only by keeping internal accounts in [E:run.claude-haiku-5.5.t1.no_context.wrong_kept_internal], and only 7 of 27 [E:run.claude-haiku-5.5.t1.no_context.wrong_tz_only] [E:run.claude-haiku-5.5.t1.no_context.wrong] were the time zone alone. Confidently wrong answers rose to 5 [E:run.claude-haiku-5.5.t1.no_context.confidently_wrong].
<!-- cited:end -->

Haiku is noisier than Opus without context: 8 questions changed outcome under `no_context`, against 3 for Opus. With the full pack there was again nothing to vary.

### Which context earned its place

| Component | `claude-opus-5.5` | `claude-haiku-5.5` | Evidence |
|---|---|---|---|
| Definitions + ground rules (`definitions.md`) | **Essential, and sufficient.** | **Essential, and sufficient.** | Both models went from 13–15 correct without it to 40/40 with it, in both trials. Schema + definitions alone scored 40/40 for both. On the holdout, its definition of an order caught a trap nobody had documented. |
| Schema catalog (`schema.md`) | **Marginal.** Fewer queries and shorter runs, no reliable accuracy change. | **Marginal.** Same pattern. | 15 then 13 correct vs 13 then 14 without it (Opus); 13 then 15 vs 14 then 13 (Haiku). The one abstention it seemed to cause flipped in the second trial. |
| Known-traps notes (`traps.md`) | **Ceremony**, once the ground rules are written. | **Ceremony**, once the ground rules are written. | `schema_definitions` 40/40 for both, even though Haiku fell for the traps with no context. |
| `answer-from-definitions` skill | **Ceremony.** Dropping it also cut queries per question. | **Ceremony.** Same. | `context_no_skill` 40/40 for both. |
| Reconcile step | **Ceremony on this set.** About double the time, nothing caught. | **Ceremony on this set.** About double the time, nothing caught. | Four runs of 34 reconciles and two holdout runs of 10; none changed an answer. Its value can't show when full context leaves nothing to catch. |

### How the predictions held up

1. *Schema fixes units and uninstrumented abstentions but not business rules.* **Half right.** Units were never a problem even with no context, and business-rule errors were untouched. The apparent abstention on sessions didn't survive a second trial.
2. *Definitions drive the gain on ambiguous questions; the traps file drives duplicates and partial periods.* **Wrong on the second half.** The definitions file drove everything. For both models the traps file added nothing once the one-line rules were in definitions, and Opus handled duplicates with no documentation at all.
3. *The skill mainly turns confident errors into caveated ones.* **Wrong premise.** Without context both models were already caveating most misses. Context raised accuracy instead of changing confidence, and the skill made no measurable difference for either model.
4. *Reconciliation catches duplicate and join errors, not definitional ones, at about double the cost.* **Untestable here.** There were no errors left to catch for either model. The time cost was about double, as predicted.
5. *No condition is perfect on the DST time-zone trap.* **Wrong.** Given the rule in writing, every full-context answer from both models handled it.

The surprise is the second-order point. A strong model is a better data profiler than I assumed, and a worse mind-reader; a weaker model is worse at both. But one short page of written conventions and ground rules closed the gap for both, and everything layered on top of it was ceremony on this set.

## Predictions, written before any run

Recorded now so the results can't be rationalised afterwards. None of these is a finding.

1. `schema_only` will fix units and most uninstrumented-data abstentions (the catalog says "cents" and lists what exists) but not refunds attribution, the activity definition or the reporting time zone, because those are business rules, not column facts.
2. The definitions file will carry most of the gain on ambiguous questions; the traps file will carry most of the gain on duplicates and partial periods. `schema_definitions` vs `context_no_skill` tests this.
3. The `answer-from-definitions` skill will mainly move errors from confidently wrong to caveated or abstained, rather than raise accuracy.
4. Reconciliation will catch duplicate and join errors (a second route usually disagrees) but not definitional errors (both routes share the misreading), and will roughly double cost per question.
5. No condition will be perfect on the time-zone trap around the DST change.

**Decision rule for "ceremony".** A context component is ceremony if removing it changes neither accuracy nor the confidently-wrong rate by more than the 95% CI of the paired difference, while costing more tokens. A component that only moves the materially-correct rate by less than its CI is reported as "cosmetic" for decision-making.

## Holdout: a trap nobody wrote down

The first limitation below is the obvious attack on the 40/40: the context pack documents exactly the traps I planted, so full context partly measures instruction-following. The holdout tests that directly with one new trap the pack never mentions.

**The trap.** A payment client sometimes submits a purchase twice. The second submission is a *new* event: new `event_id`, same `order_id` and amount, a few seconds to three minutes later. Deduplicating on `event_id`, the ground rule the pack spells out, doesn't remove it. Counting one row per `order_id` does. That matches the pack's own definition ("Order: one deduplicated purchase event, identified by `order_id`"), so the gold answers don't move the goalposts. Nothing in `schema.md`, `definitions.md`, `traps.md` or the skills was changed.

<!-- cited:start -->
- The holdout warehouse is the main one plus 628 re-submitted purchase events [E:holdout.resubmitted_events]. Every other row is identical.
- 10 questions [E:holdout.n_questions] change when only the new rule is switched off [E:holdout.live_resubmitted_orders], and those 10 are the holdout set. The error is not small: counting re-submissions overstates February gross revenue by 5.3% [E:holdout.t02.event_dedup_error_pct] ($129,181 [E:holdout.t02.event_dedup] against $122,665.44 [E:holdout.t02.gold]).
<!-- cited:end -->

One other question, `t13` (user actions in January), also changes on this warehouse because a re-submission is a distinct purchase event. Whether that counts as a "user action" is genuinely ambiguous, so `t13` was left out before any run. Every remaining question has the same gold answer on both warehouses (checked in the tests).

**Runs.** The 10 questions under `no_context`, `full_context` and `full_context_reconcile`, for both models, one trial: 60 answers.

### Holdout predictions, written before any holdout run

Committed before the first holdout agent started. None of these is a finding.

1. **Full context will fail on money.** The seven money questions (`t02`, `t03`, `t04`, `t05`, `a03`, `a05`, `a07`) are naturally computed as sums over `event_id`-deduplicated purchase rows, which double-counts re-submissions. Prediction: under `full_context`, each model gets at least 5 of the 7 wrong, and at least 4 of those equal the gold answer with only the re-submission rule switched off.
2. **Order counts will survive by accident.** For the three order-count questions (`t01`, `t15`, `a06`), `COUNT(DISTINCT order_id)` is the natural query and is immune to the trap. Prediction: at least 2 of the 3 right per model under `full_context`. So `full_context` scores between 2 and 5 of 10 per model.
3. **Reconciliation will catch little.** The reconcile skill's second route for money is "an orders CTE with refunds joined on `order_id`", which only exposes the trap if that CTE is grouped by `order_id`. Prediction: reconciliation changes at most 2 holdout answers per model, and `full_context_reconcile` lands within 2 of `full_context`.
4. **No context stays bad.** Without context the time zone and the definitions still break most of these questions. Prediction: at most 2 of 10 correct per model.

**What would change my mind.** If `full_context` scores 8 or more of 10 for a model, that model applied the written definition of an order rather than the dedup recipe, and the instruction-following objection is weaker than I think. If reconciliation recovers 3 or more answers for a model, it earns its place for traps nobody has documented, which is the one job I argued it might have.

### Holdout results

<!-- cited:start -->
| Condition | Opus correct | Opus queries per question | Haiku correct | Haiku queries per question |
|---|---|---|---|---|
| no_context | 0 [E:run.claude-opus-5.5.holdout.t0.no_context.correct] | 5.2 [E:run.claude-opus-5.5.holdout.t0.no_context.sql_per_q] | 0 [E:run.claude-haiku-5.5.holdout.t0.no_context.correct] | 4.4 [E:run.claude-haiku-5.5.holdout.t0.no_context.sql_per_q] |
| full_context | 10 [E:run.claude-opus-5.5.holdout.t0.full_context.correct] | 3.9 [E:run.claude-opus-5.5.holdout.t0.full_context.sql_per_q] | 10 [E:run.claude-haiku-5.5.holdout.t0.full_context.correct] | 3.6 [E:run.claude-haiku-5.5.holdout.t0.full_context.sql_per_q] |
| full_context_reconcile | 10 [E:run.claude-opus-5.5.holdout.t0.full_context_reconcile.correct] | 4.1 [E:run.claude-opus-5.5.holdout.t0.full_context_reconcile.sql_per_q] | 10 [E:run.claude-haiku-5.5.holdout.t0.full_context_reconcile.correct] | 3.2 [E:run.claude-haiku-5.5.holdout.t0.full_context_reconcile.sql_per_q] |

- **Full context caught the undocumented trap, for both models.** Every answer was correct, and every reconcile matched its first route [E:run.claude-opus-5.5.holdout.t0.full_context_reconcile.reconcile_match] [E:run.claude-haiku-5.5.holdout.t0.full_context_reconcile.reconcile_match], so reconciliation changed nothing [E:run.claude-opus-5.5.holdout.t0.full_context_reconcile.reconcile_changed] [E:run.claude-haiku-5.5.holdout.t0.full_context_reconcile.reconcile_changed].
- **No context failed for the old reasons, not the new one.** Opus missed all 10 and caveated all 10 [E:run.claude-opus-5.5.holdout.t0.no_context.caveated_wrong]; none of its misses is explained by the re-submission rule alone [E:run.claude-opus-5.5.holdout.t0.no_context.wrong_resubmit_only], and 5 are the time zone alone [E:run.claude-opus-5.5.holdout.t0.no_context.wrong_tz_only]. Haiku missed all 10, 2 of them confidently [E:run.claude-haiku-5.5.holdout.t0.no_context.confidently_wrong]; one miss is the re-submission rule alone [E:run.claude-haiku-5.5.holdout.t0.no_context.wrong_resubmit_only].
<!-- cited:end -->

**Why full context caught it.** The agents noticed the anomaly: nearly every full-context answer's logged checks mention purchase rows that share an `order_id` but not an `event_id`. What told them which count was right was the pack's definition of an order as "one deduplicated `purchase` event, identified by `order_id`", and most of their logged assumptions cite it. One Opus answer records: "Orders deduplicated by order_id (per definition); 628 orders had duplicate purchase rows with different event_ids". Several also caveated the answer with the event-id-only figure, so a reader could see the trap.

So the holdout shows something narrower and more useful than "context generalises": **a definition written at the right grain generalises to quirks its author never imagined.** The pack never said "watch out for re-submitted payments"; it said what an order *is*, and that was enough. It does not show that context handles a trap no definition touches, such as a currency mix-up on some rows. That remains untested, and it is where I'd still expect reconciliation, or nothing, to help.

### How the holdout predictions held up

1. *Full context will fail on money.* **Wrong.** Neither model got any of the seven money questions wrong. I expected the agents to follow the `event_id` dedup recipe; they followed the definition of an order instead.
2. *Order counts will survive by accident.* **Right, but for a different reason.** All three were right for both models, but the predicted 2–5 of 10 overall was far too low.
3. *Reconciliation will catch little.* **Held, trivially.** It caught nothing because full context had left nothing to catch.
4. *No context stays bad.* **Held.** Zero of 10 for both models.

By my own preregistered rule, the instruction-following objection is weaker than I thought: both models cleared 8 of 10. On this evidence, full-context agents weren't only following recipes; they applied the definitions to data the recipes didn't anticipate.

## Limitations

1. **The context pack documents exactly the traps I planted.** That makes `full_context` an upper bound on what context can do, and part of what it measures is instruction-following: the ground rules in `definitions.md` spell out each fix. The holdout answers part of this: a trap the pack never mentions was still caught, because a definition covered it. A trap that no definition touches is still untested, and that is the case for reconciliation over documentation.
2. **Synthetic data and one author.** The traps, definitions and gold queries are mine. A definition I wrote ambiguously would show up as model error. The pandas cross-check in the tests reconciles a sample of gold answers by an independent route, but not all of them.
3. **Small n.** 40 questions gives wide intervals. Each model ran two trials of the core conditions; the ablations ran once per model, and the holdout ran once on 10 questions with one planted trap. Only large effects are distinguishable from noise, and the second trials showed individual answers do flip in the lighter conditions.
4. **Status is a proxy for confidence.** "Confidently wrong" relies on the model's own choice of `answered` vs `answered_with_caveat`. Models calibrate that differently, and the same model labelled the same wrong value differently across trials.
5. **Scalar answers only.** The set grades numbers, not charts, narratives or the quality of a written insight. The cited-memo skill is checked for traceability, not for being a good memo.
6. **Two models from one family, run through Copilot.** The models were pinned, but sampling settings like temperature couldn't be. Each agent also had Copilot's own system prompt and tools on top of the protocol. Models from other families may fail differently.
7. **Isolation was by instruction, not enforcement.** The agents had general file access and were told to stay in their folder. Logs and post-run audits after every batch found no stray files in the bundles or the repo. In the first run, one agent ran its first command from the repo folder, created and deleted an empty work folder, then redid its work in the right place. File *reads* outside the folder can't be audited. The bundles sat outside the repo and contained no answers, so the main exposure was reading another condition's context folder. Nothing in the logs or the answers suggests that happened.
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
#   add --trial 1 (and a new --out) when importing a repeat trial of the same model
# holdout: --variant holdout builds bundles on data/analyst_holdout.db for the 10 holdout questions
python src/cli.py bundle --root <another folder> --python <python> --variant holdout \
    --conditions no_context,full_context,full_context_reconcile
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
| `src/analyst_eval/warehouse.py` | Builds the trap-laden warehouse from case 01's generator, and the holdout warehouse with one undocumented trap |
| `src/analyst_eval/gold.py`, `questions.py`, `answer_key.py` | Definitions as views, the 40 questions and the holdout subset, the answer keys with measured traps |
| `src/analyst_eval/agent.py`, `conditions.py`, `runners.py` | Agent loop, the conditions, pluggable model runners (Anthropic, OpenAI-compatible, replay) |
| `src/analyst_eval/agent_runs.py`, `bundle_tool.py` | Blind bundles for Copilot-agent runs, the logged analyst tool, log import and validation |
| `src/analyst_eval/reconcile.py`, `grading.py`, `runs.py`, `report.py` | Data-diff, grading, run persistence and replay validation, results tables |
| `src/analyst_eval/evidence.py`, `memo_lint.py` | Evidence for this memo and the linter that checks it |
| `questions/answer_key.json`, `answer_key_holdout.json` | Gold and naive answers and live traps per question, for each warehouse (regenerated and compared in CI) |
| `results/` | `evidence.json` (memo evidence) and `summary.md` (per-condition results) |
| `runs/` | Saved, validated model runs |
