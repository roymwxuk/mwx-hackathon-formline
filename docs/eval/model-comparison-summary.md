# gpt-4.1-mini vs gpt-6-luna: full comparison (2026-10-22)

Eight complete runs of the same 90 typed questions, all hand-scored with the same rubric
(scorer: Claude). Details: [model-comparison-results.md](model-comparison-results.md) (method,
criteria, per-case analysis), [name-resolution-results.md](name-resolution-results.md) (the name
fix), [model-comparison-metrics.md](model-comparison-metrics.md) (automatic metrics),
[model-comparison-scores.json](model-comparison-scores.json) (per-case scores).

## The 90 questions

| Source | Count |
|---|---|
| Original 75-case set (the first 38, plus 37 harder cases from Codex) | 75 |
| Codex's answerable additions (`a37_01`–`a37_10`) | 10 |
| New: false premises about the overturned goal (`var01`–`var05`) | 5 |

74 English, 16 Japanese. They split into two groups:

- **61 answerable**: the viewer needs a real answer from the facts.
- **29 behaviour**: the right move is to clarify, decline or correct the question (ambiguous
  or unknown names, out of scope, prompt injection, false premises, wrong club, impossible game
  windows, guarantees).

61 + 29 = 90 is the split of the questions; a perfect run scores 61 + 29 = 90 / 90.

## How the totals are counted

- **Relevant or correctly handled** = answerable questions with a relevant answer + behaviour
  questions scored "correct" (weak and wrong do not count). Example: 59 + 26 = 85 / 90.
- **Strict** = the same, but an answerable question counts only if it is also fully grounded
  (every claim true). Never higher than the first total. Example: 58 + 26 = 84 / 90.

## Results

| Configuration | Run | Relevant or correctly handled | Strict (also grounded) | Answerable relevant (of 61) | Behaviour correct / weak / wrong (of 29) | Latency median / p90 | Model calls | Cost per run |
|---|---|---|---|---|---|---|---|---|
| **gpt-4.1-mini** (baseline) | a | 80 | 78 | 58 | 22 / 4 / 3 | 5.3 / 9.1 s | 297 | ~¥44* |
| | b | 84 | 81 | 60 | 24 / 3 / 2 | 5.5 / 9.8 s | 301 | ~¥44* |
| **gpt-4.1-mini + name fix** | a | **85** | **84** | **59** | 26 / 2 / 1 | 5.5 / 9.2 s | 292 | ¥44 |
| **Luna, 400 output tokens** | a | 81 | 79 | 57 | 24 / 4 / 1 | 6.9 / 14.0 s | 287 | ~¥12* |
| | b | 81 | 79 | 57 | 24 / 4 / 1 | 7.1 / 12.0 s | 287 | ~¥12* |
| **Luna, 1,000 output tokens** | a | 82 | 79 | 57 | 25 / 3 / 1 | 6.9 / 13.4 s | 282 | ¥12 |
| | b | 82 | 81 | 56 | 26 / 2 / 1 | 7.6 / 15.0 s | 280 | ¥12 |
| **Luna, 1,000 + name fix** | a | **85** | 83 | 57 | **28 / 1 / 0** | 6.5 / 11.6 s | 269 | ¥12 |

\* These runs did not log tokens; cost estimated from later runs with similar token use. Logged
runs: gpt-4.1-mini about 679,000 input and 9,500 output tokens (about $0.29); Luna about
700,000 input, 21,000 output of which 12,000–13,000 reasoning (about $0.08). List prices:
gpt-4.1-mini about $0.40 / $1.60, gpt-6-luna $0.10 / $0.50 per 1M input / output tokens.

## Reading it

- **A tie at the top.** With the name fix both models score 85 / 90. gpt-4.1-mini is slightly
  ahead strict (84 vs 83) and on answerable questions (59 vs 57); Luna is ahead on behaviour
  (28 correct, 0 wrong).
- **The name fix helped more than switching models**: about +3 for each model, while switching
  to Luna before the fix gave about 0 (82 vs a mean of 82).
- **gpt-4.1-mini is faster**: p90 about 9 s against 12–15 s (Luna's hidden reasoning).
- **Luna is about 3.5× cheaper**: about ¥12 per run against ¥44.
- **Different weak spots.** gpt-4.1-mini: the second hop of m01 (the team's game instead of the
  player's), occasional ungrounded extras. Luna: empty Researcher replies on some Japanese
  questions, declining partly answerable questions, "last season" for this season's goals,
  latency.
- **Open on both**: identity03 fails with Researcher prompt v4 (0 of 4 runs on gpt-4.1-mini);
  decision pending: revert to v3 or reword the line.
- **Caveat**: each "+ name fix" row is a single run, and the same configuration varied by up to
  4 points between two runs, so "85 vs 85" means about equal, not a measured tie.

## Decision

The live app stays on **gpt-4.1-mini**: it met the pre-set criteria (faster, no new false
claims) where both Luna configurations failed two of five. Luna is a credible cheaper
alternative if its latency and empty-reply issues are fixed.
