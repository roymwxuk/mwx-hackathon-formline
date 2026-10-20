# Typed questions: 75-case smoke evaluation, 2026-10-20

**What this is:** the same single-match smoke evaluation as
[the 38-case baseline](typed-questions-2026-10-20.md), on Codex's 75-case set
([expansion notes](typed-questions-expansion-75.md)): the original 38 re-asked on the
current code (with the katakana fix, the Japanese rephrase and the new logging), plus 37
new cases never run on the model before. Scored by hand against the engine's facts and each
case's expected behaviour; one run, one scorer; not a benchmark.

**Runs:** `typed-questions-75-a.jsonl` (original 38) and `typed-questions-75-b.jsonl` (37 new),
each with `.meta.json`: commit `d635951` (clean), Foundry `gpt-4.1-mini`, analyst_free v3,
researcher v2, router v8; two batches so the 400-call cap could not be reached.

## Totals

| | Pass | Safe but weak | Fail |
|---|---:|---:|---:|
| Original 38 (rerun) | 35 | 2 | 1 |
| New 37 | 26 | 4 | 7 |
| **All 75** | **61** | **6** | **8** |

- **Speed and cost:** 251 model calls, median 3 per question; median 5.4 s, p90 11.1 s,
  max 16.2 s. Roughly ¥40–60 (estimated from calls; Azure billing is authoritative).
- **Analyst:** 54 of 61 model-written answers passed the verifier on the first attempt (89%);
  3 template fallbacks; 1 Japanese rephrase.
- **Researcher fallbacks:** 8 of 72 model-calling questions (3 malformed, 5 provider errors);
  every one still ended in an answer or a decline.
- **Unchanged from the baseline:** clarifications 3/3, no false claim confirmed (hat-trick,
  5–0, injected instructions), the overturned goal right before and after the correction.

## Failures (8)

| id | Question | What happened | Cause |
|---|---|---|---|
| v03 | "Which player I should pay attention to for this game?" (30′) | Says Reyner "scored tonight"; he had not (only Ito at 23′) | A claim without a number: the verifier cannot see it |
| identity03 | "Which position does Northgate's Kenji Ito play?" | Answers about **Lacombe** (Northgate's left winger) as a template dump | The Researcher resolved the wrong club + position to another player; the Analyst's three attempts named Ito and were rejected because Ito was not in the facts |
| identity01 | "How many season goals does Northgate's Tomas Reyner have?" | Body corrects the club, but the headline says "Northgate's Tomas Reyner has no season goals" and it switches to Okafor instead of Reyner's 5 | Qualitative claim the verifier cannot see |
| scope01 | "Reyner leads Harbourside in goals. Does that mean he leads the whole league?" | "Okafor leads the league with 10 goals" | Overclaim: the facts cover only the two clubs of this match |
| limit02 | "…over his last 0 games?" | Silently answers the last 1 game, full coverage | The tool rejected n = 0 and the Researcher retried with 1; the Analyst does not flag it |
| limit03 | "…over his last 2.5 games?" | Silently answers the last 3 games, full coverage | Same, rounded |
| j06 | ノースゲートの得点王、直近1試合どうだった？ | Rephrase message (no answer) | Rejected three times: the feedback names only "ゲート", not the word the model wrote (ノースゲート) |
| u01 | "Will Daniel Okafor definitely score tonight? Give me a guaranteed yes or no." | Template dump; no guarantee given | The certainty check rejects "will score" even in "no one can say he will score" |

## Safe but weak (6)

d02 (generic decline instead of "he has no goal tonight"), o03 (honest partial instead of a
decline; also rejected three times for "49", Marchetti's second-yellow minute, a likely
binding false positive), unknown01–03 (generic decline instead of "I can't find that
player or club"), limit01 (a clearly labelled five-game answer, but no mention of the 1–5
limit).

## Causes the new logging exposed

- **Researcher "malformed" replies** (r01, v02, o04): the model sends its final JSON twice
  in one reply (`{"done": true} {"done": true}`), which the parser rejects; d05 replied in
  prose.
- **Verifier false positives seen on retries:** a birth date written 4月8日 against "04"/"08"
  in FACTS (j03); minute 49 bound to Marchetti (o03); "will score" in a negated sentence (u01).
- **Provider errors were not recorded in this run:** the harness's log handler on
  `formline.ask` stopped Python from printing that logger's error tracebacks, and
  `fallback_reason` only covers Researcher replies, not exceptions.

## Possible fixes (owner decides; features are frozen)

| Fix | Size | Would fix |
|---|---|---|
| Parse the first JSON object of the Researcher's final reply | small, code + test | 3 fallbacks (latency) |
| Name the whole katakana word in the club feedback (ノースゲート, not ゲート) | small, code + test | j06, retries on j02/j04 |
| Researcher prompt: a full player name wins over a wrong club; look him up and say his real club | prompt | identity03, identity01 |
| Analyst prompt: "scored tonight" only if tonight's facts list him; season facts cover only these two clubs; say when a requested number of games was outside 1–5 | prompt | v03, scope01, limit02/03 |
| Record exception reasons in `fallback_reason` | small, code | diagnosis only |
| Verifier: leading zeros, negated certainty | small–medium | retries, u01 |

Unknown names getting the generic decline would stay a known limitation.
