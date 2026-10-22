# Finding: an unknown player name answered with another player's facts

Found in the 90-case evaluation ([results](typed-questions-90-results.md)), case `unknown03`.
Status: **open**, not fixed.

## What happened

The question names a player who does not exist in the league:

> ゾラン・ベルスコの今季の得点数は？ ("How many goals has Zoran Belsko scored this season?")

Both 90-case runs (`b60e843`) gave the same confident answer, first attempt, verified:

> ゾラン・ベルスコはNorthgate Rovers所属で、今季10得点を記録しています。チームの最多得点者です。
> ("Zoran Belsko plays for Northgate Rovers, has scored 10 goals this season and is the team's top
> scorer.")

Those are Daniel Okafor's facts (Northgate's top scorer, 10 goals) attached to a person who does
not exist. The expected behaviour is to say the name cannot be found in this league, or to ask
for the correct name.

## Why it got through

| Step | What it does | Why the invented name passed |
|---|---|---|
| Name resolution (`router.player_clarification`) | Asks "which player do you mean?" when a name matches several known players | A name that matches **no** player is not handled; the question goes to the model |
| Researcher | Picks fact lookups | With no player to look up, it fetched `season_leaders`, whose facts name Okafor as Northgate's top scorer with 10 goals |
| Analyst | Writes the answer from the facts | Attached those facts to the name in the question |
| Verifier: numbers | Every number must be in FACTS | "10" is in FACTS |
| Verifier: players | Rejects known players who are not in the facts pack | Compares against the league's player list; an unknown name is on no list |
| Verifier: binding | Numbers in a clause must belong to the player that clause names | Runs only for known players; a clause naming nobody known is skipped |
| Verifier: clubs | Only tonight's clubs, or clubs FACTS name | "Northgate Rovers" is tonight's club |

Every value in the answer is true; only the subject is invented. A verifier that checks values
against facts cannot see an invented identity. The two English unknown-name cases (unknown01
"Milo Vexford", unknown02 "Ashfen Wanderers") got the generic scope message instead: safe, but
not the "name not found" reply either.

## Evidence

| Run | Outcome | Lookups | Analyst |
|---|---|---|---|
| `typed-questions-90-a.jsonl` | answered, verified | `season_leaders` | first attempt, no rejections |
| `typed-questions-90-b.jsonl` | answered, verified | `season_leaders` | first attempt, no rejections |
| `typed-questions-75-b.jsonl` (Oct 20) | fallback error, no answer | none | — |

## Proposed fix (not started; plan first)

1. **Before any model call**, the same place ambiguous names are clarified: if the question
   contains a person-like name (a katakana run with "・", or capitalised words in English) that
   matches no league player or club, reply "I can't find <name> in this league" in the viewer's
   language. No model call, deterministic, like the existing clarification.
2. **In the verifier**, as a backstop: reject an answer whose subject is a katakana or
   capitalised name that is neither a known player, a known club, nor a word in FACTS.

Tests: unknown01–03 decline with the name-not-found reply; real players in either script
(伊藤健二, Tomas Reyner, ダニエル・オカフォー) and katakana club words are not caught; the 99.3 %
card catch rate and the 90-case answerable results do not drop.
