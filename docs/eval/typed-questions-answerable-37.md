# Answerable Q&A evaluation: 27 → 37

This corrects the scope of the earlier extra-10 handoff. The goal is **37 answerable questions**, comprising the original 27 plus 10 supported factual questions, not the earlier separate challenge set.

## Files

- `typed-questions-answerable-37.json`: complete 37-case input. The first 27 question objects are unchanged from the original 38, excluding `ambiguous`, `out_of_scope` and `hostile`, following the historical relevance denominator.
- `typed-questions-answerable-37-additions.json`: just the new ten (`a37_01`–`a37_10`, 7 EN / 3 JA).
- `typed-questions-answerable-37-reference.json`: deterministic fact packs for all 37, event/version snapshots, preparation commit and consumed data hashes. Multi-player questions have separate lookup packs for each player.

## New questions

1. Two-club season goal leader → his three-game goals and shots.
2. Both clubs' goal leaders → each player's three-game goals, shots and shots on target.
3. Both players' stronger-foot average speeds tonight versus their own season norms; no derived arithmetic required.
4. Current score, scorer and Reyner's current goal count.
5. Compare Reyner's and Okafor's season goal totals.
6. Harbourside's goal leader and all joint assist leaders.
7. Okafor's last three opponents/results and total goals.
8. Okafor's three-game shooting totals in Japanese.
9. Two-club season goal leader → recent totals in Japanese.
10. Harbourside's joint assist leaders in Japanese.

Every addition requires an answer from available facts. No prediction, hypothetical sparse sample, missing-data request or false premise is required. Some wording/combinations overlap existing coverage; this is a single-match smoke evaluation, not a held-out benchmark.

## Execution and scoring

Claude handles execution on the intended fixed implementation. Use one complete 37-case run with a fresh cache/output path and record actual code commit, prompt versions, deployment, dataset hash, data hashes, per-case outcomes/calls/cache hits/latency. The current main-workspace runner has no dataset flag: explicitly select this input and hash it in metadata; do not overwrite the existing default dataset or earlier results.

Follow `typed-question-review-rubric-v1.md`: report relevance **out of 37**, with original 27 and new 10 subtotals. Score grounding separately, including headlines, identity bindings, scope and estimate wording. Refusal on an answerable addition fails relevance. A verifier flag alone is not evidence of correctness. Review all frozen lookup packs, not just the runner's single `gold` argument set. Additional claims require evidence at the same snapshot.

Do not add historical 27/27 to a separately run ten and call it a single 37-case result. The saved original rerun report in the `eval/rerun-38` checkout reports 27/27; its semantic scoring has not been independently repeated here.

The earlier `typed-questions-extra-10*` artifacts and Claude's evaluation findings remain valid historical challenge material and must be preserved. They are **not** the ten additions for this denominator.

## Local verification

Prepared without a model runner: confirmed 27 original objects unchanged, 37 unique IDs, ten distinct new texts versus the original 38, and successful event/version resolution and deterministic reference generation for all 37. No new model/cloud calls. Preparation uses local `b8e3b8f`; evaluation must record its actual implementation version. The facts use application builders, not an independent oracle.
