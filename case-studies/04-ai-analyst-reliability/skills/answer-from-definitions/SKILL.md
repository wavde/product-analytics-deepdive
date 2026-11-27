---
name: answer-from-definitions
description: Answer a business metric question from the team's metric definitions and the warehouse, or abstain when the definitions or data don't support it. Use for any "how many / what was / what percent" question against the storefront warehouse.
---

# Answer from definitions

The goal is a number someone can act on without re-deriving it. That means the metric is
pinned to a written definition before any SQL is written, and the answer says which
checks were run.

## 1. Turn the question into a metric spec

Before querying, write down:

- **Term**: which definition in `definitions.md` this is (e.g. "active users in February"
  is MAU; unqualified "revenue" is net revenue).
- **Period**: exact business-date bounds in `America/Los_Angeles`, Monday-start weeks.
  For relative periods, read `etl_watermark` first and use the latest *complete* period.
- **Population**: non-internal users; user-initiated events only.
- **Unit**: count, USD, percent (0-100) or ratio.

If you can't fill in a line, stop here:

- The term maps to nothing in the definitions and nothing in the schema -> abstain.
- The data isn't instrumented (sessions, channel, cost, demographics) -> abstain.
- The period ends after the watermark or before the data starts -> abstain.

Abstaining with a reason is a correct answer. A plausible number built on an invented
definition is the most expensive kind of wrong, because nobody checks it.

## 2. Build the query in two layers

1. A base CTE that applies every ground rule once: one row per `event_id`, internal
   accounts removed, user-initiated events only, `event_ts` converted to business time
   before any date cast. For money, an orders CTE with refunds joined on `order_id`.
2. The metric on top of that base. Keep the metric layer short enough to read aloud.

## 3. Pre-flight checks (run them, don't just assert them)

- Duplicates: `COUNT(*)` vs `COUNT(DISTINCT event_id)` on the base.
- Internal: the base has no `is_internal = true` users.
- Event mix: the `event_name` values feeding the metric are the ones you intended.
- Time zone: one timestamp near the period boundary lands on the expected business date.
- Units: dollars are cents / 100; percents are 0-100.
- Plausibility: compare with a neighbouring period; a 3x jump is a bug until proven
  otherwise.

## 4. Report

Return the answer contract with `status`:

- `answered`: the definition applied cleanly and the checks passed.
- `answered_with_caveat`: you had to make a judgement call the definitions don't settle;
  name it in `assumptions`.
- `abstained`: step 1 stopped you; say why in `assumptions`.

List the checks you actually ran in `checks`. `final_sql` must reproduce `value` exactly.
