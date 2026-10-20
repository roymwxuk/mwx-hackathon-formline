# Typed-question set expanded to 50

The active `backend/scripts/typed_questions.json` contains **50 unique cases: 42 English,
8 Japanese**. The original 38 case objects are unchanged and also preserved byte-for-byte
in `typed-questions-original-38.json` (matching the historical baseline dataset hash).
Existing baseline/rerun JSONL, metadata, review scores and reports are unchanged.

**Status:** new snapshots and reference facts checked locally with no inference. No new
real-model evaluation has run. The old 26/27 relevance figure remains a historical
38-case result, not a result for this expanded dataset or current production code.

## Twelve additions

| IDs | Gap covered | Expected result |
|---|---|---|
| t01–t03 | Player-stat rollback across an exact VAR boundary, rather than another score-only test | Reyner shots / on target / goals: **5/3/0**, then **6/4/1**, then **6/3/0** |
| m01 | Assist-leader lookup rather than another top-scorer lookup | Umar Okonjo: 5 season assists; last game 0 goals, 0 assists, 1 shot on target |
| m02 | Same section for two players; preserve identity and recent window | Last three: Reyner 1 goal / 4 on target; Okafor 2 goals / 5 on target |
| m03 | Same team and section with different window arguments | Northgate last result lost 1–3; last five 1W/1D/3L, goals 8–13 |
| u01–u02 | Unsupported certainty and absent biography/contract evidence | Decline guaranteed scoring prediction; decline invented height/salary |
| j06 | Katakana club alias, colloquial wording and one-game chaining in Japanese | Resolve Northgate → Okafor; last game 1 goal, 6 shots, 4 on target |
| j07 | Informal Japanese and distinct nationality/birthplace facts | Okafor: born Cardiff, Wales; nationality Spain |
| s01 | Club-qualified surname resolves existing ambiguity in a single request | Harbourside's Garrow = Pablo; last game 0 goals/shots, 37/41 passes |
| s02 | Full-name identity and profile retrieval before a player has shot | Anders Ingleby: nationality Brazil; born Sendai, Japan |

There is no conversational history in the application. s01/s02 replace the two proposed
multi-turn tests; each must work as an independent request with all needed identity context.
All identities and biographies are synthetic.

## Snapshots and evidence

t01 is pinned to `evt_3100936/1` immediately before the shot; t02 to the initial goal
`evt_3100937/1`; t03 to its correction `evt_3100937/2` immediately on arrival. The change
from goal to off target reduces goals and on-target shots while leaving total shots at six.
Earlier snapshots must not use the final corrected result. These add a different invariant
from existing score-only d09/d10 and much later 66/89-minute checks.

The other nine cases are pinned to `evt_3100037/1` (the existing early two-minute snapshot),
so recent/season questions cannot accidentally be answered with future live events.

Every new case has `expected_decisions`, `scoring_criteria`, hard `constraints`, a compatible
`gold` lookup and a `reference` pointer. `typed-questions-expansion-reference.json` contains
all deterministic reference lookups, event/version, dataset hash and consumed-data hashes.
For m02/m03, compare against **both** reference packs: the old runner's single `gold`
selection cannot represent two separate player IDs or two windows of the same section.
The runner preserves the reference pointer and constraints in each result row.

Reference facts use the application's deterministic builders, not an independent oracle.
Tests rebuild seed-2026 data in a temporary directory and check all 12 references; VAR
counts are additionally checked directly against replayed shot outcomes. No shared demo
data, prompts, verifier rules, routing or production behavior changed.

## Scoring before any new model run

Apply `typed-question-review-rubric-v1.md` and the case-specific criteria. The new cases
expect 10 answers and 2 declines; a generic refusal on an answerable case is a failure.
Allow alternative lookup paths and wording when the requested facts are correct. Do not
require tool-name equality with reference lookups. For Japanese, canonical English club
names are acceptable; mixed-language fact dumps that omit requested facts fail.

Hard checks: exact VAR-state counts and player identity; separate players and recent/season
windows; no invented missing attributes or guaranteed outcomes. Record numerical errors,
decision mismatches, relevance, grounding, coverage and language separately. A template
does not pass just because `verified` is true. Uncertain judgments require review.

The saved structured scoring report and its 27-answerable denominator apply only to the
original baseline. Do not apply that denominator to the 50-case set: declare the new
denominators from expected decisions before scoring. Do not splice new answers or reruns
into historical aggregate results. Record the dataset hash and selected IDs for each run.

## Local checks and future runs

From `backend/`, without any Azure calls:

```sh
.venv/bin/pytest -q tests/test_typed_question_dataset.py tests/test_typed_question_scoring.py
```

The existing evaluation command now selects 50 cases by default. A future paid run needs
the owner's separate go, a new output filename, and a frozen committed dataset. The runner
still has its existing 400-call cap; 50 cases could theoretically consume more than that
under repeated failures, so budget exhaustion must be reported rather than scored as a
model-quality failure. No token-based spend cap or measured cost is claimed here.

To select only the new cases in a later authorized run, pass:

```text
--only t01,t02,t03,m01,m02,m03,u01,u02,j06,j07,s01,s02
```

Test success here proves fixture/reference consistency, not real-model answer quality.
