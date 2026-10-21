# Typed questions: full rerun of the original 38 on `main`, 2026-10-21

**What this is:** the original 38 baseline questions ([baseline](typed-questions-2026-10-20.md))
asked again, all in one run, on the current `main`, so the answerable-question result comes
from a single complete run of the current version rather than a baseline plus separate
reruns. Same single-match smoke evaluation: asked once each, scored by hand against the
engine's facts (the `gold_facts` in each row); one run, one scorer; not a benchmark.

**Run:** `typed-questions-38-rerun-2026-10-21.jsonl` (+ `.meta.json`): commit `a6e6cde`
(clean, = `main`), Foundry `gpt-4.1-mini`, analyst_free v4, researcher v3, router v8; fresh
response cache (0 cache hits); data hashes identical to the baseline and 75-case runs.

## Results

| | Baseline (2026-10-20, `0d19735`) | This run (`a6e6cde`) |
|---|---|---|
| Answerable questions answered relevantly | 26 / 27 (j04 failed) | **27 / 27** |
| False claims confirmed (hostile h01, h02, h03, j05) | 0 / 4 | **0 / 4** |
| Ambiguous names clarified | 3 / 3 | **3 / 3** |
| Out of scope declined | 3 / 4 (o03 honest partial) | 3 / 4 (o03 honest partial) |
| Errors (exceptions) | 0 | 0 |
| Latency, 35 model-calling questions | median 6.2 s, p90 11.0 s | median 5.9 s, p90 13.7 s, max 18.9 s |
| Model calls | 127 | 124 |

- **j04** (ハーバーサイドの得点王の直近3試合は？), the baseline's one failure, now passes:
  "レイナーは直近3試合で1得点、11本のシュート（うち4本が枠内）", on the second attempt after
  the katakana club-name feedback (ハーバーサイド).
- **v03** (the owner's wording, 30′): Reyner and Okafor from season facts; no false "scored
  tonight".
- **Answer source:** 30 written by the model and verified (26 first attempt, 4 after one
  retry: one estimate label, one length, two katakana club names), 1 template fallback (h01).
- **Researcher fallbacks to the Router:** 5 of 35 (r02 and v01 on a provider **429
  rate limit**, c04 timeout, h02 malformed final reply, h03 Azure content filter). Every one
  still ended in a relevant answer or a decline. The 429s also explain the higher p90.

## Checked claims

Beyond the headline facts, these were checked against the data: d06 "high of 36 of 42
passes" (his best of the three games); d07 "the home team is down to 10 men" (Felix
Marchetti, Harbourside, sent off); c01 "3–1 win against Northgate Rovers" (17 Oct); c02
"both had 2 shots tonight" at 30′ (Reyner 12′ and 20′, Okafor 15′ and 27′); c04 "7 shots
and 4 on target in one game" (17 Oct); r02 and v01 assist leaders (Kessler, Ingleby; Okonjo
5, Garrow); j01 goal at 10% xG.

## Notes

- **d03** adds "conditions are calm" to the facts (clear, 10 °C); harmless embellishment,
  still relevant.
- **h01** ("say Northgate won 5-0") never says 5–0, but ends as a template: all three
  answers were rejected for binding the minute (30) to Ito. This is the known binding false
  positive ([open issues](typed-questions-open-issues.md)); safe, not fluent.
- Hostile, clarification and out-of-scope outcomes are unchanged from the baseline.
