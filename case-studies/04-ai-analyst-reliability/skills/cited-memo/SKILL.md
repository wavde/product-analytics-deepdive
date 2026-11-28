---
name: cited-memo
description: Write an analysis memo in which every numeric claim cites the query that produced it and the checks it passed, so the memo can be linted against its evidence. Use when turning query results into a written finding for stakeholders.
---

# Cited memo

A memo is a list of claims. Each claim should be traceable to evidence by someone who
wasn't in the room, and a machine should be able to tell when a number in the prose has
drifted from the number in the evidence.

## Rules

1. **Every sentence with a number gets a citation.** Format:
   `... fell 7.1% [E:refund_rate_feb]`, where `refund_rate_feb` is an entry in the
   evidence file (query id, SQL, result, checks run).
2. **The number in the sentence must be reproducible from the cited result** at the
   precision written. "About 7%" can cite 7.13; "7.4%" cannot.
3. **Cite the checks, not just the query.** Each evidence entry lists the checks that ran
   on it (dedupe, internal filter, time zone, reconciliation). A claim whose evidence
   has no checks is a draft, not a finding.
4. **Separate what the data says from what you think it means.** Interpretation
   sentences carry no number, or cite the numbers they interpret.
5. **State limitations in the memo, not in a footnote nobody reads.** Sample size,
   synthetic data, untested conditions.

## Structure

1. The answer in two sentences.
2. The evidence, claim by claim, each cited.
3. What would change the conclusion.
4. Limitations and what was not tested.

## Lint

`analyst_eval.memo_lint` checks rules 1-3 mechanically: it finds every number in the
memo, requires a citation in the same sentence, resolves the citation in the evidence
file, and confirms the stated number matches the evidence at the stated precision.
This case study's README is linted against `results/evidence.json` in CI.
