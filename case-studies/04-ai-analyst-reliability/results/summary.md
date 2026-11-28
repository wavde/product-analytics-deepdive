# Results

## github-copilot / claude-opus-5.5

Trials: 0. Files: `full_github-copilot_claude-opus-5.5.jsonl`.

| Condition | n | Accuracy | Materially correct (±1%) | Confidently wrong | Caveated wrong | Over-abstained | Matched naive answer | Lift vs no_context (95% CI) | Same outcome across trials | SQL calls per q | Tokens in / out per q | Cost per q | Cost per correct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| no_context | 40 | 32.5% | 72.5% | 2.5% | 65.0% | 0.0% | 0.0% | - | n/a | 3.8 | n/a | n/a | n/a |
| schema_only | 40 | 37.5% | 80.0% | 2.5% | 60.0% | 0.0% | 0.0% | +5.0 pp (+0.0, +12.5) | n/a | 2.5 | n/a | n/a | n/a |
| full_context | 40 | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% | 0.0% | +67.5 pp (+52.5, +82.5) | n/a | 2.0 | n/a | n/a | n/a |
| full_context_reconcile | 40 | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% | 0.0% | +67.5 pp (+52.5, +82.5) | n/a | 1.9 | n/a | n/a | n/a |

Accuracy by trap (questions where the trap is live):

| Trap | no_context | schema_only | full_context | full_context_reconcile |
|---|---|---|---|---|
| definition | 0.0% | 12.5% | 100.0% | 100.0% |
| duplicates | 0.0% | 10.0% | 100.0% | 100.0% |
| internal_accounts | 0.0% | 4.8% | 100.0% | 100.0% |
| not_instrumented | 75.0% | 100.0% | 100.0% | 100.0% |
| partial_period | 50.0% | 50.0% | 100.0% | 100.0% |
| refunds | 0.0% | 12.5% | 100.0% | 100.0% |
| system_events | 0.0% | 8.3% | 100.0% | 100.0% |
| timezone | 0.0% | 0.0% | 100.0% | 100.0% |
| units | 100.0% | 100.0% | 100.0% | 100.0% |
