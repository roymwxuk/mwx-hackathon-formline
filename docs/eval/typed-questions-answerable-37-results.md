# Answerable Q&A, 37 cases: Foundry results (2026-10-22)

One complete run of [typed-questions-answerable-37.json](typed-questions-answerable-37.json)
(the original 27 answerable questions plus Codex's 10 supported additions;
[dataset notes](typed-questions-answerable-37.md)) on `gpt-4.1-mini`, fresh response cache,
no cache hits. Single synthetic match, one run, one scorer: a smoke evaluation, not a
benchmark. Scored by hand against every lookup in
[typed-questions-answerable-37-reference.json](typed-questions-answerable-37-reference.json),
headlines included; claims outside those packs were checked against facts rebuilt with the
application's builders at the same event and version.

| | |
|---|---|
| Commit | `a0e4392` (clean); differs from `main` only in the certainty check |
| Prompts | analyst_free@v4, researcher@v3, router@v8 |
| Dataset | `typed-questions-answerable-37.json`, sha256 `aa71405b1a04…` |
| Output | `typed-questions-answerable-37-a.jsonl` (+ `.meta.json`) |
| Calls / latency | 129 model calls; median 5.5 s, p90 9.3 s, max 13.0 s |

## Results

| | Relevance | Grounding (answered cases) |
|---|---|---|
| Original 27 | **25 / 27** | 24 / 25 |
| New 10 | **9 / 10** | 9 / 10 |
| **All 37** | **34 / 37** | **33 / 35** |

The two original cases without an answer (d02, c04) made no claim, so they are left out of
the grounding denominator.

## Failures

| ID | Relevance | Grounding | What happened |
|---|---|---|---|
| d02 "How fast was Reyner's goal?" | **fail** | n/a | The Researcher returned "cannot answer"; the viewer got the generic scope message instead of "Reyner did not score tonight". The Oct 21 rerun answered it correctly |
| c04 "Was Reyner's goal better than his usual finishes?" | **fail** | n/a | Same: six lookups, then "cannot answer". The Oct 21 rerun answered it (after a timeout fallback) |
| a37_07 Okafor's last three opponents and scorelines | **fail** | pass | **Verifier false positive.** The model named Thornmoor United and Corranvale City, which are in the `player_recent` FACTS, but the typed-answer entity check rejects clubs not in tonight's match. Three rejections, then a template with the 2 goals but no opponents |
| d03 weather | pass | **fail** (minor) | "Conditions are calm and ideal for play": the facts say only "clear, 10 °C" |
| a37_03 shot speed vs norm | pass | **fail** (criterion) | 99 vs 88 and 85 vs 81 km/h are correct, but the norms are not qualified as estimates, as the case requires. The fact string itself carries no estimate marker |

d02 and c04 are not caused by this branch's change: the Analyst and the verifier never ran on
them, and the only code difference from `main` is the certainty check. They are run-to-run
variation in the Researcher's decision on false-premise questions, which a single run
cannot measure.

## Checked and correct

Claims outside the frozen packs, rebuilt at the same snapshot: Harbourside down to 10 men at
89′ (d07, d10), Reyner and Okafor 2 shots each at 30′ (c02), Northgate 1 won, 1 drawn,
3 lost, 8 for and 13 against (j02), Reyner's goal in the 3–1 win on 17 Oct (c01, j04).
a37_09 (same wording as ext10_09) now has a correct headline. a37_10's Researcher errored
and the Router fallback produced a correct answer (13.0 s).

## a37_07 after the fix

The entity check now allows a club that FACTS name (`5f130ad`; a club absent from FACTS is
still rejected). Rerun of a37_07 alone (`typed-questions-answerable-37-fix-a07.jsonl`,
3 calls): first-attempt answer, "Corranvale City (2–2), Thornmoor United (0–3), and
Harbourside Athletic (1–3). He scored 2 goals": relevant and grounded. This is a
single-case recheck; the 34 / 37 above stays the result of the complete run.

## Run b (second complete run, after the fix)

`typed-questions-answerable-37-b.jsonl`, commit `b706554` (clean, includes the past-opponent
fix), same dataset hash, fresh cache; 125 model calls, median 4.7 s, p90 8.2 s.

| | Relevance | Grounding (answered cases) |
|---|---|---|
| Original 27 | **26 / 27** | 25 / 26 |
| New 10 | **10 / 10** | 9 / 10 |
| **All 37** | **36 / 37** | **34 / 36** |

- **d02** failed again: the Researcher returned "cannot answer" after one lookup.
- **c04** passed: "Reyner Has Not Scored Tonight Despite Several Shots", with his best chance
  (14 %, model estimate) and his last three games.
- **a37_07** and **a37_10** passed on the model's own answer.
- Grounding: a37_03 again leaves the norms unqualified; r02 adds "Garrow for chances
  created", which FACTS do not hold (they give his assists and shots).
- Checked outside the packs: Okafor scored in 3 of Northgate's last 5 games (j02), his best
  passing game was 36 of 42 (d06), both players had 2 shots on target at 30′ (c02).

### Across both runs

| | Run a | Run b |
|---|---|---|
| Relevance | 34 / 37 | 36 / 37 |
| Grounding | 33 / 35 | 34 / 36 |

35 of 37 questions were relevant in both runs. **d02 failed both times**; c04 failed once.
Together with the earlier runs, d02 has answered cleanly in 1 of 5 runs: the one stable
weakness is a false-premise question about the overturned goal, which the Researcher tends to
decline instead of correcting. a37_07's run-a failure was the verifier bug fixed in between.

## Not to be combined

This is one 37-case run. It does not combine the Oct 21 27 / 27 with a separate ten. The
extra-10 challenge results ([extra-10 results](typed-questions-extra-10-results.md)) are a
separate set.
