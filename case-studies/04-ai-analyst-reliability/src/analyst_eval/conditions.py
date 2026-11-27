"""The four experimental conditions and the prompts they produce.

Every condition gets the same protocol, the same SQL tool and the same permission to
abstain, so differences in confidently-wrong rate come from context, not from one arm
being told it may say "I don't know".
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from analyst_eval import CONTEXT_DIR, SKILLS_DIR

PROTOCOL = """\
You are a data analyst answering one business question from a DuckDB database
(DuckDB SQL dialect). You can only learn about the data by querying it.

To run a read-only query, reply with exactly one fenced block and nothing else:
```sql
SELECT ...
```
You will get back up to 50 rows. You may run at most {max_sql} queries.

When you are done, reply with exactly one fenced json block:
```json
{{"status": "answered" | "answered_with_caveat" | "abstained",
 "value": <number, or null if abstained>,
 "unit": "count" | "usd" | "percent" | "ratio",
 "final_sql": "<the query that produces value>",
 "assumptions": ["..."],
 "checks": ["..."]}}
```
- "answered": you are confident the number answers the question as asked.
- "answered_with_caveat": you gave a number but a judgement call could change it.
- "abstained": the question cannot be answered reliably from this data.
Percents are 0-100. Money is US dollars. Give the exact value, not a rounded one.
"""

RECONCILE_INSTRUCTIONS = """\
RECONCILE STEP. Before your answer is accepted, follow the reconcile-results skill below.
Reply with exactly one ```sql block: an independent query for the same metric that takes
a different route from your final_sql. It must return the metric in the same shape as
your final_sql (same number of columns, value columns in the same positions).

{skill}
"""

RECONCILE_FOLLOWUP = """\
Data-diff of your final_sql (primary) against the independent query:
{report}

Now give your final answer as a ```json block. You may run more queries first if you need
to resolve a mismatch. If the routes disagree and you cannot explain why, use
"answered_with_caveat" or "abstained".
"""


@dataclass(frozen=True)
class Condition:
    name: str
    description: str
    context_files: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    reconcile: bool = False


CONDITIONS: dict[str, Condition] = {
    c.name: c
    for c in [
        Condition("no_context", "Question and protocol only; the model explores the database."),
        Condition("schema_only", "Adds the column-level catalog.", ("schema.md",)),
        Condition(
            "full_context",
            "Adds metric definitions, known data traps and the answer-from-definitions skill.",
            ("schema.md", "definitions.md", "traps.md"),
            ("answer-from-definitions",),
        ),
        Condition(
            "full_context_reconcile",
            "Full context, then a mandatory independent recomputation and data-diff.",
            ("schema.md", "definitions.md", "traps.md"),
            ("answer-from-definitions",),
            reconcile=True,
        ),
        # Optional ablations, not run by default: they split "full context" into its parts
        # so a component that doesn't earn its tokens can be called ceremony.
        Condition("schema_definitions", "Schema plus metric definitions; no traps, no skill.",
                  ("schema.md", "definitions.md")),
        Condition("context_no_skill", "Schema, definitions and traps; no skill.",
                  ("schema.md", "definitions.md", "traps.md")),
    ]
}
CORE_CONDITIONS = ["no_context", "schema_only", "full_context", "full_context_reconcile"]


def read_skill(name: str) -> str:
    text = (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    return text.strip()


def system_prompt(condition: Condition, max_sql: int) -> str:
    parts = [PROTOCOL.format(max_sql=max_sql)]
    for f in condition.context_files:
        parts.append(f"<context file=\"{f}\">\n{(CONTEXT_DIR / f).read_text(encoding='utf-8')}"
                     "\n</context>")
    for s in condition.skills:
        parts.append(f"<skill name=\"{s}\">\n{read_skill(s)}\n</skill>")
    return "\n\n".join(parts)


def reconcile_prompt() -> str:
    return RECONCILE_INSTRUCTIONS.format(skill=read_skill("reconcile-results"))


def prompt_hash(condition: Condition, max_sql: int) -> str:
    text = system_prompt(condition, max_sql)
    if condition.reconcile:
        text += reconcile_prompt() + RECONCILE_FOLLOWUP
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
