---
license: mit
language:
- en
task_categories:
- text-classification
pretty_name: evalroute-tasks
size_categories:
- n<1K
tags:
- evalroute
- task-routing
- coding-agents
---

evalroute-tasks
===============

A small human-labeled corpus for training and evaluating `evalroute`'s
task→lane router. Each row is one real coding/research/writing task with the
lane a human asserts it belongs to. Tier 1 (task → lane) is the only required
label today; the schema leaves room for tier 2 (task → arm outcome) and tier 3
(task → done artifact) so contributors can backfill later without a format
break.

Status: zero to one. One contributor, 54 rows, four of nine lanes. Per lane:
routine-coding 30, dl-ml-research-engineering 13, alignment-reasoning 10, prose 1;
hard-agentic-coding, long-doc-reading, web-research, math-first-principles and
orchestration have none yet. 24 rows are real tasks pinned in one dispatcher's
ledger (mostly coding briefs), 30 are hand-written tier-a taskset rows. n is small
and the mix reflects one person's work — that is the point of publishing it:
your work shapes your router, and the shared encoder is only as broad as this
file. The trained encoder is `keppy/evalroute-lane-encoder`; the outcomes
flywheel (lane/arm/verdict, no text) is `keppy/evalroute-flywheel`.

Tiers
-----

| Tier | Question            | Keys                                     | Required |
|------|---------------------|------------------------------------------|----------|
| 1    | which lane?         | id, text, label, source, contributor, week | yes    |
| 2    | which arm, and did it work? | arm, verdict, method, n          | optional (all-or-none) |
| 3    | how was done judged? | checker / rubric / reference (at most one) | optional |

Row example
-----------

```json
{"id": "keppy:a3f9c1", "text": "add a CLI verb that reads the ledger and prints per-lane counts",
 "label": "routine-coding", "source": "ledger-pinned", "contributor": "keppy", "week": "2026-W40",
 "arm": "z-ai/glm-5.3-flash@medium", "verdict": "pass", "method": "measured", "n": 10,
 "checker": null, "rubric": null, "reference": null}
```

The publish gate (three steps, all must pass)
---------------------------------------------

1. Mechanical validation: `python scripts/validate.py tasks/*.jsonl` checks
   id/text/lane/source/contributor/week format, tier-2 and tier-3 coherence,
   and a secret/PII/hostname regex gate over `text` and tier-3 strings.
2. Denylist: if `private_terms.txt` exists in the repo root (git-ignored) or
   you pass `--private-terms <file>`, any case-insensitive whole-word hit fails
   the row. Keep employer/project terms you must not publish in that file.
3. Human review: run `python scripts/review.py tasks/<you>.jsonl`, read every
   numbered row, compute the batch sha, add
   `reviewed: <sha>  <date>  <contributor>` to `REVIEWED.md`, then open a PR.
   `scripts/upload.py` refuses to touch Hugging Face unless `REVIEWED.md`
   contains a line for every file's sha.

How to contribute
-----------------

1. Fork/branch, add your own file `tasks/<your-handle>.jsonl` (one JSON row per
   line; the file stem and row-id prefix must be your handle).
2. Run `python scripts/validate.py tasks/<your-handle>.jsonl` — it must exit 0.
3. Run `python scripts/review.py tasks/<your-handle>.jsonl`, actually read the
   rows, and add the printed `reviewed:` line to `REVIEWED.md`.
4. Open a PR. A reviewer re-runs validate and diff-checks your rows.

What is not here
----------------

No paraphrases: train F showed paraphrases that outnumber real rows pull the
classifier toward the paraphrase dialect. No ledger exports without review —
a row lands here only after a human decided the text is safe to publish. No
personal or employer details: names, internal hostnames, credentials, and
project-denialist terms are caught by the gate, but judgment is still yours.

License
-------

MIT, see LICENSE (copyright 2026 keppy).
