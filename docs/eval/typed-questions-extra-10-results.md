# Ten additional Q&A variants: Foundry results (2026-10-21)

The ten cases from [typed-questions-extra-10.md](typed-questions-extra-10.md), asked once on
`gpt-4.1-mini` through `answer_free`, with a fresh response cache (no cache hits). This is a
single-match smoke evaluation, reported separately from the post-fix 27 / 27 on the original
38. Scored by hand against every lookup in
[typed-questions-extra-10-reference.json](typed-questions-extra-10-reference.json), headlines
included.

| Run | Commit | Cases | Model calls | Files |
|---|---|---|---|---|
| a | `7055443` | all 10 | 41 | `typed-questions-extra-10-a.jsonl` |
| fix-v10 … fix-v10-4 | `2ec383d` … `05fe921` | ext10_10 | 6, 6, 5, 4 | `typed-questions-extra-10-fix-v10*.jsonl` |

Prompts: analyst_free@v4, researcher@v3, router@v8. Data hashes match the reference file.
Run a: median 6.9 s, max 23.7 s (ext10_10, timeout fallback).

## Scores

| ID | Relevance | Grounding | Notes |
|---|---|---|---|
| ext10_01 | pass | pass | Okafor 10; last three: 2 goals, 12 shots, 5 on target |
| ext10_02 | pass | pass | Reyner 1 / 11 / 4, Okafor 2 / 12 / 5, each bound to the right player |
| ext10_03 | **fail** | pass | The model computed +11 and +4 correctly; the verifier rejects derived numbers not in FACTS, so three rejections led to a template that lists Reyner's facts and only "Okafor." |
| ext10_04 | pass | pass | 1–0, Ito; "Reyner has not scored". Weak: does not mention the overturned goal |
| ext10_05 | **fail** | **fail** | Accepts the false premise ("Reyner's hat-trick stands out despite no goals tonight") and invents "his hat-trick in other matches". Passed the verifier |
| ext10_06 | pass | pass | Reyner 5 goals; Kessler and Ingleby 2 assists each |
| ext10_07 | pass (cautious) | pass | Two shots are not enough; no invented sample |
| ext10_08 | pass | pass | 2 goals, 12 shots; minutes and ratings marked unavailable; coverage partial |
| ext10_09 | pass | **fail** | Body correct (Okafor 10; 2 goals, 12 shots). Headline 今季最多得点はオカフォーとレイナー names both as top scorer |
| ext10_10 | run a: fail; after fix: pass (cautious) | after fix: minor fail | See below |

**Answerable cases (01–06, 08, 09; 07 and 10 excluded as Codex specified): relevance 6 / 8,
grounding 6 / 8, both 5 / 8.** Cases 07 and 10 are cautious and do not assert certainty.

## ext10_10 and the certainty check

Run a fell back to a template after three rejections for "guaranteed". All three attempts were
honest refusals ("No guaranteed next scorer…", "No player can be guaranteed to score next").
The cause was the narrower certainty check committed just before the run (`245acfb`), which
only accepts an explicit denial right before the claim. Fixed in three steps, each rerun on
ext10_10: "no guaranteed", "no player can be guaranteed", "do not guarantee who will score",
"no data guarantees", "no definite next scorer can be guaranteed", "no data guaranteeing".
Replayed offline over all 262 saved English answers, the final check agrees with the old one
on every answer, while still rejecting the audit cases ("Ito has not been tested and Okafor
will definitely score", "Nobody can deny he will score"). Catch rate unchanged: 99.3 %,
certainty 88 / 88, 0 false positives.

The final rerun (`05fe921`) answered on the second attempt. The first was rightly rejected
(role placeholders CHANCE_B / CHANCE_C, body over 260 characters, xG without estimate
wording). The answer calls Reyner's 14 % chance "blocked"; the facts say saved.

## New findings

1. **False premise accepted (ext10_05).** The answer invents a hat-trick that no fact
   supports. The verifier checks numbers and names, not claims without numbers. A
   deterministic check like the "scored tonight" one (a hat-trick or brace claim must match
   the player's goals tonight) would catch this case.
2. **Derived differences rejected (ext10_03).** Correct arithmetic (99 − 88 = 11) is not in
   FACTS, so it is rejected. Options: add the per-player difference to the facts pack, or let
   the verifier accept a difference of two FACTS values of the same player.
3. **Template drops the second player (ext10_03).** The fallback lists only "Okafor." after
   Reyner's facts.
4. **Wrong club not caught.** A rejected ext10_10 attempt said "Northgate's Reyner" (he plays
   for Harbourside). It was rejected for another reason; the entity check does not bind
   players to clubs in typed answers.
5. **Role placeholders** (CHANCE_B, SCORER_A) leaked in 7 of 14 ext10_10 Analyst attempts
   across the five runs (all in the reruns). The jargon check caught each one.
