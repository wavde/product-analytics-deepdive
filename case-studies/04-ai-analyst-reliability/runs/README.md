# Saved runs

One JSONL file per live evaluation run, written by `python src/cli.py run`. Each file has
a `meta` line (provider, model, prompt hashes, answer-key hash, pricing), one `answer`
line per condition x question x trial (full transcript, final answer, token counts), and
an `end` line.

CI replays every file here against a fresh warehouse build (`python src/cli.py validate`)
and fails if any SQL result, data-diff or parsed answer differs, or if the context,
skills or answer key changed since the run. After adding a run, regenerate
`results/summary.md` with `python src/cli.py report` and update the README's results
section.

No runs have been recorded yet.
