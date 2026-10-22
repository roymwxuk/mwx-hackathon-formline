# Finding: a two-hop question answered about the team instead of the player

Found in the 90-case evaluation ([results](typed-questions-90-results.md)), case `m01`.
Status: **open**, not fixed.

## What happened

> Who leads Northgate in assists this season, and how did he do in his last game?

The question has two hops: find the assist leader (Umar Okonjo, 5 assists), then **his** last
game (0 goals, 0 assists, 1 shot on target, 27 of 32 passes). Both 90-case runs (`b60e843`)
answered the first hop and swapped the subject of the second:

> Okonjo has the most assists for Northgate with 5 this season. In **their** last game, Northgate
> lost 1–3 to Harbourside Athletic, with Okafor scoring their only goal.

"He" became "their": the answer reports the team's last result, not Okonjo's game. Every
sentence is true, and the answer marks its coverage "full".

## Why

The Researcher chose the wrong tool for the second hop:

| Run | Prompt | Lookups | Result |
|---|---|---|---|
| `typed-questions-75-b.jsonl` (Oct 20) | researcher@v2 | `get_season_leaders` → `get_player_recent` (Okonjo, 1 game) | **correct**: "no goals or assists, 27 of 32 passes, 1 shot on target" |
| `typed-questions-90-a.jsonl` (Oct 22) | researcher@v3 | `get_season_leaders` → `get_team_recent` (Northgate, 1 game) | team result |
| `typed-questions-90-b.jsonl` (Oct 22) | researcher@v3 | `get_season_leaders` → `get_team_recent` (Northgate, 1 game) | team result |

With only the team's facts, the Analyst wrote about the team. Its "full" coverage claim was
not true for the question asked.

researcher@v3 (2026-10-20) added "a full player name wins over a wrong club" (eval identity03).
It may have shifted "Northgate … he" toward the club, but one earlier run is not enough to say
v3 caused it; it may also be run-to-run variation.

## Why the verifier cannot see it

The verifier checks that every number and name in the answer is in the retrieved facts. Here
they all are: 5 assists, 1–3, Okafor, Harbourside Athletic. A wrong subject built from true
facts is a relevance failure, not a factual one, so only the evaluation catches it. It is the
same class of failure as [the unknown-name case](unknown-name-hallucination.md), the other way
round: there the facts were right and the subject invented; here the subject is real but the
facts are about someone else.

## Proposed fix (not started; plan first)

1. **Researcher prompt:** when a question asks how *he / she / the player* did after naming a
   leader, call `get_player_recent` for the id that the first tool returned, not
   `get_team_recent`. Add m01 as a worked example in the prompt header's changes line.
2. **Deterministic check, cheap:** if the question asks about one player's game ("how did he
   do", "his last game") and the lookups contain no player-level section for the player the
   answer names, mark coverage partial instead of trusting the Analyst's "full".

Tests: a fake-tool test where the second hop is `get_team_recent` and the coverage is downgraded;
m01 rechecked three times on the model, and m02 / m03 / c01 (other two-hop cases) not worse.
