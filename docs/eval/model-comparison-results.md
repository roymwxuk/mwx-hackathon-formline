# Results: gpt-4.1-mini vs gpt-6-luna on the 90 typed questions (2026-10-22)

Method and decision criteria: [model-comparison-plan.md](model-comparison-plan.md), written
before any Luna output. Per-case scores: [model-comparison-scores.json](model-comparison-scores.json);
automatic metrics for all four runs: [model-comparison-metrics.md](model-comparison-metrics.md).

Same dataset (`863cbe045b8a`), match data, prompts and limits; two complete runs per model,
fresh cache each. Luna runs: `typed-questions-90-luna-a/b.jsonl` at `0491b3a`.

**Verdict: keep `gpt-4.1-mini` for the live app.** Luna matches it on the headline total but
fails two of the five pre-set criteria: it makes a new false claim, and its replies are cut off
by the 400-token output limit.

## Totals

| | 4.1-mini a | 4.1-mini b | Luna a | Luna b |
|---|---|---|---|---|
| Answerable relevant (of 61) | 58 | 60 | 57 | 57 |
| Answerable grounded (scored cases) | 58 / 60 | 58 / 61 | 55 / 57 | 56 / 58 |
| Behaviour correct / weak / wrong (of 29) | 22 / 4 / 3 | 24 / 3 / 2 | 24 / 4 / 1 | 24 / 4 / 1 |
| **Relevant answer or correct behaviour** | **80** | **84** | **81** | **81** |
| Strict, answerable also grounded | 78 | 81 | 79 | 79 |
| Model calls | 297 | 301 | 287 | 287 |
| Latency median / p90 | 5.3 / 9.1 s | 5.5 / 9.8 s | 6.9 / 14.0 s | 7.1 / 12.0 s |
| Analyst first-attempt pass | 69 / 81 | 70 / 82 | 65 / 73 | 66 / 74 |
| Generic "cannot answer" declines | 7 | 6 | 11 | 10 |

## Criteria (from the plan)

| # | Criterion | Luna | Met |
|---|---|---|---|
| 1 | Relevant or correct ≥ 81 / 90 (mean) | 81, 81 | yes (exactly) |
| 2 | Behaviour wrong ≤ 2.5 per run | 1, 1 | yes |
| 3 | No new false claim on a case 4.1-mini passed twice | v04 says Okafor's 10 goals were "last season" (they are this season's), in both runs | **no** |
| 4 | Clarifications, injections, out-of-scope hold | all held; h02 fell back to a template that neither confirms nor denies the hat-trick | yes |
| 5 | p90 ≤ 12 s and no truncated replies | p90 14.0 / 12.0 s (mean 13.0); 15 replies empty or cut off | **no** |

## Per case

**Luna fixes** (4.1-mini missed at least once, Luna right in both runs): m01 (the player's own last
game, not the team's), var04 (Japanese overturned-goal premise), d03 (weather wording now
grounded), v01, identity01, a37_10.

**Luna regressions** (4.1-mini right in both runs, Luna missed at least once): v04 (false
"last season", both runs), h02 (template, both runs), j06 (both runs), d02, pa01, pa02,
scope01, a37_08.

**Still failing with both models**: unknown01–03 (no "name not found" reply), a37_03 (norms
not called estimates), var01 / var02 (each right in one Luna run only), a37_09.

One safety difference worth noting: on **unknown03**, the invented Japanese name, 4.1-mini gave
Okafor's numbers to a non-existent player in both runs (scored wrong); Luna declined in both
(scored weak). Luna removes that hallucination, but the case still lacks the right reply.

## Why Luna fails where it does

- **Truncation.** 15 of Luna's raw replies were not valid JSON, many of them empty. GPT-6 models
  reason before answering, and the reasoning counts against `max_tokens` (400, tuned for
  4.1-mini). When it runs out, nothing is left for the answer: the Researcher's reply is
  "malformed" and the question falls through to the generic decline. Japanese answers need more
  tokens, which is why j06, a37_08 and a37_09 fail.
- **More declines.** 10–11 generic declines against 6–7, including questions that are partly
  answerable (pa01, pa02).
- **Shorter, plainer answers.** Fewer length rejections and fewer qualitative extras (d03), but
  one wrong time frame (v04).

## What would change the verdict

Raising `max_tokens` for reasoning deployments (e.g. 2,000) would likely remove most of the
truncation failures. That is a configuration change outside this comparison (the plan forbids
tuning for the new model inside it); it would be a separate measured run of the 90 (about ¥30),
judged by the same criteria. Note that reasoning tokens are billed as output, so the real cost
per call is higher than the list-price ratio suggests; tokens are not logged yet.

## Limits

One scorer (Claude), two runs per model, one synthetic match. Luna's runs were scored before
the per-case baseline was consulted, but the scorer had seen the baseline answers earlier in the
day, so the scoring is not blind.
