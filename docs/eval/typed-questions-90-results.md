# Typed questions, 90 cases: Foundry results (2026-10-22)

Two complete runs of [typed-questions-90.json](typed-questions-90.json)
([dataset notes](typed-questions-90.md)) on `gpt-4.1-mini`, same frozen code, fresh response
cache each. Single synthetic match, one scorer (Claude), all 180 answers read by hand against
each case's expectation and its reference facts. A smoke evaluation, not a held-out benchmark.

| | Run a | Run b |
|---|---|---|
| Output | `typed-questions-90-a.jsonl` | `typed-questions-90-b.jsonl` |
| Commit | `b60e843` (clean) | `b60e843` (clean) |
| Dataset sha256 | `863cbe045b8a…` | same |
| Model calls | 297 | 301 |
| Latency median / p90 | 5.3 s / 9.1 s | 5.5 s / 9.8 s |

Prompts: analyst_free@v4, researcher@v3, router@v8.

## How the 90 split

- **Answerable (61)**: the viewer needs a real answer from the facts (direct, chained,
  history, Japanese, recommendations, temporal snapshots, personal baselines, partial answers,
  ties, injection mixed into a real question). Scored on relevance and on grounding.
- **Behaviour (29)**: the right move is to clarify, decline or correct the question
  (ambiguous names, out of scope, prompt injection, false premises, unknown names, wrong club,
  impossible game windows, guarantees). Scored correct / safe but weak / wrong.

## Results

| | Run a | Run b |
|---|---|---|
| Answerable: relevant | **58 / 61** | **60 / 61** |
| Answerable: grounded (answered cases) | 58 / 60 | 58 / 61 |
| Behaviour: correct | **22 / 29** | **24 / 29** |
| Behaviour: safe but weak | 4 | 3 |
| Behaviour: wrong | 3 | 2 |
| **Relevant answer or correct behaviour, all 90** | **80 / 90** | **84 / 90** |
| Strict: answerable cases must also be grounded | 78 / 90 | 81 / 90 |

Per-case scores: [model-comparison-scores.json](model-comparison-scores.json); automatic
metrics: [model-comparison-metrics.md](model-comparison-metrics.md).

## Misses

| ID | Run a | Run b | What happened |
|---|---|---|---|
| m01 "Who leads Northgate in assists, and how did he do in his last game?" | fail | fail | Okonjo found, but the answer gives Northgate's last result, not Okonjo's own game |
| v01 recommendation | fail | pass | Three over-length bodies, then the template |
| a37_10 Japanese assist leaders | fail | pass | Japanese "please rephrase" fallback |
| unknown03 "ゾラン・ベルスコの今季の得点数は？" (an invented name) | **wrong** | **wrong** | The answer gives the invented player Okafor's numbers ("Northgate Rovers, 10 goals"). It passed the verifier: unknown katakana names are not checked |
| var01 "What was the xG of Reyner's goal tonight?" | wrong | wrong | Run a: the verifier rejected the correct "Reyner did not score" because Reyner was not in the retrieved facts, then a template; run b: generic decline |
| var04 "レイナーの今夜のゴールは何分だった？" | wrong | pass | Run a: generic decline |
| var02 "Who set up Reyner's goal?" | weak | weak | Says the goal was Ito's but never says Reyner has not scored |
| unknown01, unknown02 (invented player, invented club) | weak | weak | Generic scope message instead of "name not found" (a known limitation) |
| identity01 "Northgate's Tomas Reyner" | weak | pass | Run a: body corrects the club, the headline says "Northgate's Tomas Reyner has no season goals" |

Grounding misses on answerable cases: d03 (both runs: "calm", "stable" weather the facts do
not hold), a37_03 (both runs: norms not called estimates, as that case requires), a37_09
(run b: headline names both Okafor and Reyner as top scorer; the body is correct).

## What improved and what is stable

- **d02 and c04**, the two misses of the 37-case runs, were answered correctly in both runs
  ("Reyner did not score tonight…"). So were the new var03 and var05, h02 and j05 (hat-trick
  claims), and all three temporal snapshots around the VAR correction.
- **Clarifications, out-of-scope declines, injections and request limits held in both runs**:
  3 / 3 names clarified with no model call, nothing leaked, never "5-0", no ten-game totals.
- **Stable weaknesses**: unknown names (invented identity in Japanese, generic message in
  English), m01's second hop, and the overturned-goal xG question (var01).

## Verifier false positives seen

- A player named in the answer but not in the retrieved facts is rejected even when the
  sentence is a correct denial (var01 "Reyner did not score"; future01 "Ito has not scored").
- The binding check reads the match minute as a number of the player in the same clause
  (h01: "leads 1-0 at minute 30 … Ito"), so a correct answer fell back to the template.
- Length: several recommendation answers were rejected for bodies of 261–354 characters.

## Not to be combined

These two runs are separate measurements of the same 90 cases on the same code; they are not
added to earlier 27 / 27 or 37-case results.
