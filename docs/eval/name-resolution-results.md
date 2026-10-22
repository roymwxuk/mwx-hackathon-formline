# Name resolution (ADR-014): model checks

Plan: [plan-name-resolution.md](../plan-name-resolution.md). Code: `453a0c7`. Same 90 cases,
rubric and reference facts as [the model comparison](model-comparison-results.md); per-case
scores in [model-comparison-scores.json](model-comparison-scores.json), metrics in
[model-comparison-metrics.md](model-comparison-metrics.md).

## gpt-6-luna, one run (owner asked for GPT-6 first)

`typed-questions-90-luna-names-a.jsonl`: 1,000 output tokens (automatic for GPT-6), Researcher
prompt v4, 269 model calls, median 6.5 s, p90 11.6 s, 695,200 input / 20,198 output tokens
(11,949 reasoning, at most 788 in one call), no reply cut off.

| | Luna 1,000 before the fix (a / b) | **Luna with the fix** |
|---|---|---|
| Relevant answer or correct behaviour | 82 / 82 | **85** |
| Strict (answerable also grounded) | 79 / 81 | **83** |
| Answerable relevant (of 61) | 57 / 56 | 57 |
| Behaviour correct / weak / wrong (of 29) | 25-3-1 / 26-2-1 | **28 / 1 / 0** |
| Latency p90 | 13.4 / 15.0 s | 11.6 s |

**The fix works**: unknown01, unknown02 and unknown03 returned `not_found` with **0 model calls**:

- "I can't find Milo Vexford among tonight's players or clubs. Check the spelling, or ask with the club name."
- "I can't find Ashfen Wanderers among tonight's players or clubs. …"
- "ゾラン・ベルスコは今夜の選手・クラブの中に見つかりません。綴りを確認するか、クラブ名を添えて質問してください。"

**Other changes against both earlier Luna runs at 1,000 tokens**

- Fixed: v02, v03 (no "last season" this time), j03, pa02, a37_09, and var01 / var02 behaviour.
- Regressed:
  - **c03** "Has Northgate's top scorer had a shot tonight?": the Researcher fetched only the
    season leaders, and the answer says tonight's shots are not in the data.
  - **r01**: "Okafor scored in each of his last two listed games"; he scored in one of them.
  - **m01**: the Researcher returned an empty final reply (the Luna tool-loop issue seen before),
    and the Router fallback did not reach Okonjo's own game.

None of the three involves a name lookup, so the new prompt line (v4) is not an obvious cause,
but one run cannot rule it out. The `gpt-4.1-mini` check below decides whether the change goes
live, since that is the live model.

## gpt-4.1-mini, one run (the live model)

`typed-questions-90-names-a.jsonl`: 292 model calls, median 5.5 s, p90 9.2 s, 678,938 input /
9,476 output tokens (no reasoning), about **$0.29 (¥44)** per run at list price.

| | Baseline a / b (before the fix) | **With the fix** |
|---|---|---|
| Relevant answer or correct behaviour | 80 / 84 | **85** |
| Strict (answerable also grounded) | 78 / 81 | **84** |
| Answerable relevant (of 61) | 58 / 60 | 59 |
| Behaviour correct / weak / wrong (of 29) | 22-4-3 / 24-3-2 | 26 / 2 / 1 |

**unknown01, unknown02, unknown03: `not_found` with 0 model calls**, the same replies as on Luna.
The invented identity of unknown03 (Okafor's numbers given to a non-existent player in both
baseline runs) is gone.

**Plan criteria**

| Criterion | Result |
|---|---|
| unknown01–03 correct | **met** |
| No case that passed in both baseline runs fails | **not met**: identity03, a37_05 (below) |
| No new false claim | met for the model's own text; identity03's template shows another player's profile |

**The two regressions**

- **a37_05** (Reyner's and Okafor's season goals): Azure returned **429 "rate limit exceeded"**
  during the Researcher's run, so the Router fallback fetched only Reyner, and the answer fell
  back to a template without Okafor. Not caused by the change. The token logs explain it: a
  90-question run sends about 680,000 input tokens in about 10 minutes (roughly 70K tokens per
  minute), above the deployment's 50K tokens-per-minute capacity.
- **identity03** ("Which position does Northgate's Kenji Ito play?"): in both baseline runs the
  Researcher called `find_player` and fetched Ito's profile. This time it fetched Northgate's
  left winger, Lacombe; the verifier rejected the answers naming Ito (not in the facts), and the
  template showed Lacombe's profile. Ito is in the squad list, so the new prompt line (for names
  *not* in it) should not apply, but one run cannot rule out that v4 shifted the Researcher.

**Also fixed in this run** against the baseline: d03, v01, a37_09, a37_10, var01, var04.

## Verdict

The deterministic fix does what it should on both models, with no model call and no false
positive over 100 saved questions. Whether Researcher v4 causes the identity03 regression is
open: three reruns of identity03 (and a37_05, to confirm the rate limit) would settle it for a
few yen. The 50K TPM capacity is enough for live viewers but not for an evaluation run at full
speed.
