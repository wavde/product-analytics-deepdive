# Results

## github-copilot / claude-haiku-5.5

Trials: 0, 1. Files: `haiku_ablation_github-copilot_claude-haiku-5.5.jsonl`, `haiku_github-copilot_claude-haiku-5.5.jsonl`, `haiku_t1_github-copilot_claude-haiku-5.5.jsonl`.

| Condition | n | Accuracy | Materially correct (±1%) | Confidently wrong | Caveated wrong | Over-abstained | Matched naive answer | Lift vs no_context (95% CI) | Same outcome across trials | SQL calls per q | Tokens in / out per q | Cost per q | Cost per correct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| no_context | 80 | 33.8% | 52.5% | 10.0% | 55.0% | 1.2% | 16.2% | - | 80.0% | 4.0 | n/a | n/a | n/a |
| schema_only | 80 | 35.0% | 61.3% | 3.8% | 61.3% | 0.0% | 3.8% | +1.2 pp (-2.5, +6.2) | 87.5% | 2.3 | n/a | n/a | n/a |
| full_context | 80 | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% | 0.0% | +66.2 pp (+51.2, +80.0) | 100.0% | 2.0 | n/a | n/a | n/a |
| full_context_reconcile | 80 | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% | 0.0% | +66.2 pp (+51.2, +80.0) | 100.0% | 2.1 | n/a | n/a | n/a |
| schema_definitions | 40 | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% | 0.0% | +66.2 pp (+51.2, +80.0) | n/a | 1.8 | n/a | n/a | n/a |
| context_no_skill | 40 | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% | 0.0% | +66.2 pp (+51.2, +80.0) | n/a | 1.5 | n/a | n/a | n/a |

Accuracy by trap (questions where the trap is live):

| Trap | no_context | schema_only | full_context | full_context_reconcile | schema_definitions | context_no_skill |
|---|---|---|---|---|---|---|
| definition | 12.5% | 6.2% | 100.0% | 100.0% | 100.0% | 100.0% |
| duplicates | 10.0% | 5.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| internal_accounts | 4.8% | 2.4% | 100.0% | 100.0% | 100.0% | 100.0% |
| not_instrumented | 87.5% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| partial_period | 25.0% | 37.5% | 100.0% | 100.0% | 100.0% | 100.0% |
| refunds | 12.5% | 6.2% | 100.0% | 100.0% | 100.0% | 100.0% |
| system_events | 8.3% | 4.2% | 100.0% | 100.0% | 100.0% | 100.0% |
| timezone | 0.0% | 0.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| units | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |

## github-copilot / claude-opus-5.5

Trials: 0, 1. Files: `ablation_github-copilot_claude-opus-5.5.jsonl`, `full_github-copilot_claude-opus-5.5.jsonl`, `full_t1_github-copilot_claude-opus-5.5.jsonl`.

| Condition | n | Accuracy | Materially correct (±1%) | Confidently wrong | Caveated wrong | Over-abstained | Matched naive answer | Lift vs no_context (95% CI) | Same outcome across trials | SQL calls per q | Tokens in / out per q | Cost per q | Cost per correct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| no_context | 80 | 33.8% | 72.5% | 3.8% | 61.3% | 1.2% | 0.0% | - | 92.5% | 3.9 | n/a | n/a | n/a |
| schema_only | 80 | 35.0% | 76.2% | 2.5% | 62.5% | 0.0% | 0.0% | +1.2 pp (+0.0, +3.8) | 95.0% | 2.2 | n/a | n/a | n/a |
| full_context | 80 | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% | 0.0% | +66.2 pp (+52.5, +80.0) | 100.0% | 1.8 | n/a | n/a | n/a |
| full_context_reconcile | 80 | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% | 0.0% | +66.2 pp (+52.5, +80.0) | 100.0% | 1.8 | n/a | n/a | n/a |
| schema_definitions | 40 | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% | 0.0% | +66.2 pp (+52.5, +80.0) | n/a | 1.6 | n/a | n/a | n/a |
| context_no_skill | 40 | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% | 0.0% | +66.2 pp (+52.5, +80.0) | n/a | 1.1 | n/a | n/a | n/a |

Accuracy by trap (questions where the trap is live):

| Trap | no_context | schema_only | full_context | full_context_reconcile | schema_definitions | context_no_skill |
|---|---|---|---|---|---|---|
| definition | 0.0% | 6.2% | 100.0% | 100.0% | 100.0% | 100.0% |
| duplicates | 0.0% | 5.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| internal_accounts | 0.0% | 2.4% | 100.0% | 100.0% | 100.0% | 100.0% |
| not_instrumented | 87.5% | 87.5% | 100.0% | 100.0% | 100.0% | 100.0% |
| partial_period | 50.0% | 50.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| refunds | 0.0% | 6.2% | 100.0% | 100.0% | 100.0% | 100.0% |
| system_events | 0.0% | 4.2% | 100.0% | 100.0% | 100.0% | 100.0% |
| timezone | 0.0% | 0.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| units | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
