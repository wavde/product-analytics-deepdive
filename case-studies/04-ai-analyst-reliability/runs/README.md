# Saved runs

One JSONL file per live evaluation run, written by `python src/cli.py run`. Each file has
a `meta` line (provider, model, prompt hashes, answer-key hash, pricing), one `answer`
line per condition x question x trial (full transcript, final answer, token counts), and
an `end` line.

CI validates every file here against a fresh warehouse build (`python src/cli.py validate`).
API runs are replayed turn by turn. Copilot-agent runs (`runner_kind: copilot-agent`) are
validated by re-executing every logged query and reconcile diff and rebuilding each graded
field from its tool log. Validation fails if any result differs, or if the context, skills,
tool or answer key changed since the run. After adding a run, regenerate
`results/summary.md` with `python src/cli.py report` and update the README's results
section.

`full_github-copilot_claude-opus-5.5.jsonl` holds 160 answers (40 questions × 4 core
conditions, one trial).
