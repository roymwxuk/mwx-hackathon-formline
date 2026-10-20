# Typed-question set expanded to 75

The active dataset contains **75 unique cases: 63 English, 12 Japanese**. This batch adds
three cases in each of the five requested categories. The first 60 objects are unchanged;
the exact parent file is preserved in `typed-questions-original-60.json`. The previous
60-case expansion was still uncommitted when this batch was added, recorded explicitly in
the new reference manifest. The original 38/50 snapshots and all existing run results,
review scores and earlier reference manifests remain untouched.

**Status:** reference and policy checks only, no new real-model evaluation. These cases
declare expected behavior; passing fixture tests is not a claim that the model passes them.
No production prompts, routing, verifier or tools changed.

## Fifteen additions

| Category | IDs | Expected behavior and verified facts |
|---|---|---|
| Valid personal baselines | base01–base03 | Compare tonight's stronger-foot **average** to the same player's season norm: Reyner **99 vs 88**, Okafor **85 vs 81**, Ito **89 vs 85 km/h**. All above norm. Preserve average/body-group qualifiers and avoid ability rankings. Ito question is Japanese. |
| Unknown entities | unknown01–unknown03 | Unrecognized English player, English club and Japanese player names: explicitly explain unavailable identity or ask for a corrected name. No guessing similar identities or invented profiles. |
| Contradictory identities | identity01–identity03 | “Northgate's Tomas Reyner,” “Harbourside's Daniel Okafor,” “Northgate's Kenji Ito”: explicitly correct the club before answering, or clarify the conflict. Actual clubs are Harbourside, Northgate, Harbourside respectively. |
| History request limits | limit01–limit03 | Requested last **10**, **0**, **2.5** games. Explain the supported whole-number range **1–5**; no silent truncation, default substitution or rounding. For 10, a clearly labeled five-game partial answer is allowed. |
| Cross-language identity | cross01–cross03 | English question with 伊藤健二 → nationality England; Japanese question with Tomas Reyner → birthplace Swansea, Wales; English question with ダニエル・オカフォー → last-game 1 goal, 6 shots, 4 on target. |

## Reference scope

The three speed comparisons are pinned to `evt_3100942/1` at 66 minutes. These are valid
comparisons of observed averages with available personal norms, not questions about the
overturned goal, a latest-shot value absent from the shooting summary, or an unavailable
conditional percentile. Expected season norms are treated as model estimates. Do not
substitute fastest-shot values or derive an unsupported ability judgment.

All other cases use `evt_3100037/1`, the early two-minute snapshot. Every case has explicit
expected decisions, hard constraints, scoring criteria and a reference pointer into
`typed-questions-expansion-75-reference.json`. That file stores dataset/data hashes,
snapshots, deterministic fact packs, negative registry checks and limit-policy references.

Unknown-entity cases have `gold: null`: absence from the loaded synthetic registry is the
evidence, not an invented response pack. Null gold also applies to invalid zero/fractional
window requests. Limit01 includes a five-game reference as an allowed **partial alternative**,
not as evidence of ten-game support. Tests verify all three requested values are rejected
by the existing tool validator. They do not send invalid values to any cloud service.

Negative entity checks cover loaded synthetic league names only, not the world. A club/player
conflict must not be silently ignored even when one full name is recognizable. A valid
clarification is allowed for such conflicts; an unrelated generic refusal does not pass.
For unknown names, a specific limitation or useful clarification is required. For invalid
windows, the allowed range must be explained; the existing generic decline alone is not
automatically scored as correct. These are declared review policies, not model results.

## Scoring and preservation

Apply the existing rubric with these explicit allowed decisions:

- Personal baselines and cross-language cases: answer the question in the requested language.
- Unknown entities: decline with a specific identity limitation or ask a useful clarification.
- Conflicting identities: correct the false club premise and answer, or explicitly clarify it.
- Ten-game request: explain limitation and decline, or answer a clearly labeled five-game
  subset with partial coverage. Zero/fractional requests: explain limitation or clarify.

Never force a particular tool path or exact prose. Mark unknown/unsupported facts separately
from numeric contradictions and infrastructure errors. Keep all three expansions' future
results separate from the saved 38-question baseline; the 26/27 relevance metric has not
been remeasured. The baseline scoring helper's historical denominator is not a denominator
for the 75-case set. No existing scores or result files were regenerated here.

The current runner selects 75 cases by default with its unchanged 400-call budget. A future
paid run needs separate authorization, a new output filename and a frozen committed dataset.
Budget exhaustion must be reported separately; neither a spend cap nor expanded-set quality
has been measured. To select just this batch in a later authorized run:

```text
--only base01,base02,base03,unknown01,unknown02,unknown03,identity01,identity02,identity03,limit01,limit02,limit03,cross01,cross02,cross03
```

Local tests rebuild synthetic data in a temporary directory, compare references across all
three batches, check stronger-foot averages directly, verify registry/conflict premises and
validate the history-limit policy. No inference:

```sh
cd backend
.venv/bin/pytest -q tests/test_typed_question_dataset.py tests/test_typed_question_scoring.py
```
