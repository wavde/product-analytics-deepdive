---
name: reconcile-results
description: Before reporting a metric, recompute it by an independent path and diff the two results, data-diff style. Use when a number is about to leave your hands, or when two people (or two queries) disagree about the same metric.
---

# Reconcile results

One query agreeing with itself proves nothing. Two queries that take different routes to
the same definition and land on the same number is the cheapest real evidence there is.

## 1. Pick a genuinely independent route

Same definition, different mechanics. Good pairs:

| First route | Independent route |
|---|---|
| Deduplicate with `ROW_NUMBER()` over `event_id` | `COUNT(DISTINCT event_id)` / `DISTINCT ON` |
| Orders from `events` | Orders from `refunds`-joined order table, or vice versa |
| Monthly total | Sum of the daily series for the same month |
| Rate computed in one statement | Numerator and denominator as separate queries, divided by hand |
| `AT TIME ZONE` conversion | Explicit UTC bounds for the business period |

Re-running the same query, or the same query with cosmetic edits, is not reconciliation.

## 2. Diff, don't eyeball

Compare the two result sets on: row count, keys present on only one side, and numeric
columns with an explicit tolerance (exact for counts, a cent for money, 0.01 points for
percents). The harness runs this diff for you and returns a report.

## 3. Classify any gap

- **Rounding**: within tolerance once both are rounded the same way. Report.
- **Definitional**: the routes encode different readings (refund date vs order date,
  UTC vs business day). Go back to `definitions.md`, decide which is right, fix the
  other, and re-diff.
- **Bug**: a missing filter or join fan-out. Fix it and re-diff.
- **Unexplained**: you can't say which is right. Report with `answered_with_caveat`,
  state both numbers and which one you trust and why, or abstain.

Never average two disagreeing numbers, and never report the one you like better without
saying a second route disagreed.
