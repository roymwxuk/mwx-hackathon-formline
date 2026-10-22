# Typed questions: the 90-case set

`typed-questions-90.json` is one input for a complete run:

| Part | Cases | Source |
|---|---|---|
| Active dataset (original 38 + 37 harder cases) | 75 | `backend/scripts/typed_questions.json`, unchanged |
| Codex's answerable additions | 10 | `typed-questions-answerable-37-additions.json`, unchanged |
| New: false premises about the overturned goal | 5 | `typed-questions-90-new-5.json` |

74 English, 16 Japanese. Reference facts: the existing reference files for the first 85,
`typed-questions-90-reference.json` for `var01`–`var05` (built with the application's fact
builders, not an independent oracle).

The five new cases target the one weakness two 37-case runs left: questions that assume
Reyner's 64′ goal, which VAR overturned ("What was the xG of Reyner's goal?", "Who set up
Reyner's goal?", "Reyner has scored twice tonight, right?", the Japanese "レイナーの今夜のゴールは
何分？", and "Is it still 2–0?" at 89′). The right behaviour is to correct the premise.

Some wordings repeat on purpose at different moments (d01 / d09 / d10 before and after the
correction, t01–t03, v01 / v03); no question repeats at the same moment. a37_09 has the same
wording as the earlier challenge case ext10_09. This is a single-match smoke evaluation with one
scorer, not a held-out benchmark.

Run: `uv run python scripts/eval_typed_questions.py --questions ../docs/eval/typed-questions-90.json
--out <new-file.jsonl> --max-calls 600`.
