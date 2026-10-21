# Ten additional Q&A challenge variants

Prepared 2026-10-21 at local `b8e3b8f`. **Not model-evaluated.**

`typed-questions-extra-10.json` contains ten cases (9 EN, 1 JA), each pinned to a received event/version, with expected decisions and scoring criteria. `typed-questions-extra-10-reference.json` freezes deterministic fact packs, source commit and local data hashes. Existing 75-case questions and historical results are unchanged.

| ID | Test | Required evidence / behavior |
|---|---|---|
| ext10_01 | Leader → recent history | Okafor: 10 season goals; last three games: 2 goals, 12 shots |
| ext10_02 | Two leaders → two histories | Reyner: 1 goal, 11 shots, 4 on target; Okafor: 2 goals, 12 shots, 5 on target over three games |
| ext10_03 | Compare personal-baseline differences | Stronger-foot averages: Reyner 99 versus 88 km/h (+11); Okafor 85 versus 81 (+4); norms are estimates |
| ext10_04 | Corrected scoreboard | 1–0, Ito only; Reyner's goal overturned |
| ext10_05 | False-premise explanation | Correct the claimed hat-trick; Reyner has zero goals tonight |
| ext10_06 | Different leaders and a tie | Reyner: 5 goals; Kessler and Ingleby: 2 assists each |
| ext10_07 | Hypothetical sparse evidence | No confident ability inference from two shots; no invented player sample |
| ext10_08 | Partial answer | Okafor: 2 goals in three games; minutes played and ratings unavailable |
| ext10_09 | Japanese chained lookup | Japanese answer; Okafor, 10 season goals, then 2 goals / 12 shots in three games |
| ext10_10 | Requested guarantee | Reject certainty about the next scorer; cautious evidence discussion or decline acceptable |

## Scoring and execution handoff

- Score relevance and factual grounding separately against all frozen reference lookups, including headlines. Correct values assigned to the wrong player fail grounding.
- A fallback or `verified=true` flag alone is not a pass. Missing requested available facts makes an answer incomplete. Cases 07 and 10 permit a clear decline; they must not inflate an answerable-question success denominator.
- These deliberately overlap existing cases as new wording/combinations; they are not a held-out independent benchmark or ten new capability categories.
- The current runner has no dataset CLI option. Do not overwrite its default 75-case file. On an authorized run, load this separate JSON and ensure metadata hashes this dataset, records the actual implementation commit/prompts/data, and uses a fresh output path/cache.
- Multi-lookup references are stored separately because the runner's `gold` field supports one argument set; consult every lookup when scoring cases 01–06 and 09–10.
- Local preparation checked ten distinct IDs, no verbatim question duplicates against the existing 75, event resolution, and successful deterministic reference generation. No model runner was instantiated. References use application fact builders, not an independent truth oracle.

Claude handles implementation and any authorized evaluation execution. Model/cloud execution still requires the owner's go. Report these ten separately from the Claude-reported post-fix 27/27 result.
