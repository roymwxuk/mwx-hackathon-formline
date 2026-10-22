# Plan: resolve names in typed questions before any model call

Status: **draft for review** (owner, then Codex). Nothing is built yet.

## Problem

A typed question that names a player or club who does not exist gets the wrong reply. Three
cases failed in **every** one of six 90-case runs, with both `gpt-4.1-mini` and `gpt-6-luna`
([model comparison](eval/model-comparison-results.md)):

| Case | Question | What happened |
|---|---|---|
| unknown01 | What is Milo Vexford's nationality? | Generic "I can only answer from this match's data…" |
| unknown02 | How did Ashfen Wanderers do in their last game? | Generic decline (Luna twice said the club "isn't in the data") |
| unknown03 | ゾラン・ベルスコの今季の得点数は？ | `gpt-4.1-mini`: the invented player was given Okafor's numbers (10 goals) and **passed the verifier**; Luna: generic decline |

The right reply is "I can't find *Milo Vexford* in either squad tonight", in the viewer's
language. unknown03 is the serious one: an invented identity built from true facts
([finding](eval/unknown-name-hallucination.md)).

## Why it happens

1. **Name resolution only handles ambiguity.** `player_clarification` (`analyst/router.py`)
   runs before any model call and asks "which player do you mean?" when a name matches several
   squad players (Garrow, Leon). A name that matches **no** player is not handled; the
   question goes to the Researcher.
2. **The model rarely searches.** The Researcher has a `find_player(name)` tool
   (`analyst/tools.py`) that already returns `{"candidates": []}` for an unknown name, but its
   prompt says to use it only when a name matches several players, and the full squad list is
   already in its prompt.
3. **There is no "not found" outcome.** The Researcher can only fetch facts or reply
   `cannot_answer`, which the code turns into the generic scope message.
4. **The verifier only knows known names.** It rejects known players who are not in the
   facts; an unknown name is on no list, so an answer attaching real facts to it passes.

## Decision: code resolves names on every question; the model searches only when code cannot

Rejected: making the Researcher call `find_player` on every question. That costs a model
round-trip (about 1–2 s and more input tokens) on most questions, uses one of its five tool
calls, and is still only a request: a model can skip it, as `gpt-4.1-mini` skipped any lookup
in unknown03.

Chosen: the deterministic pass that already scans every question for ambiguous names is
extended to classify each name it finds, before any model call:

| Result | Example | What happens |
|---|---|---|
| Resolved | "Okafor", "ダニエル・オカフォー" | Unchanged: the question goes on to the Researcher |
| Ambiguous | "Garrow", "Leon" | Unchanged: "Which player do you mean…?" (no model call) |
| Known, not in tonight's squads | a player of Elderwick Town | New: "<name> plays for <club>, which is not in tonight's match" (no model call) |
| **Unknown** | "Milo Vexford", "Ashfen Wanderers", "ゾラン・ベルスコ" | **New**: "I can't find <name> in either squad tonight. Check the spelling, or ask with the club name." (no model call) |

`find_player` stays for what code cannot resolve (typos like "Okafur", partial names); the
Researcher prompt gains one line and a new reply shape for that path.

## The hard part: deciding that a word is a name

Code may only answer "not found" when it is confident the text names a person or club. When it
is unsure, it says nothing and the question goes on as today. Rules:

- **Japanese**: a katakana run containing "・" (the full-name shape, e.g. ゾラン・ベルスコ) that
  matches no player's Japanese name or its parts.
- **English**: a run of **two or more** capitalised words (Milo Vexford, Ashfen Wanderers) that is
  not a known name. A single capitalised word is never flagged ("Okafur" goes to the
  Researcher, "January" and "Ignore" are ordinary words).
- **Allow-list of every name in the data**: all 108 league players (English and Japanese, full
  and parts), the six clubs and their short names, the referee, the venue, birthplaces and
  nationalities. These are never "unknown".
- Skip the first word of a sentence when deciding capitalisation ("Who", "Compare"),
  and strip possessives ("Harbourside's").

## Changes

| Where | Change |
|---|---|
| `analyst/router.py` | `resolve_names(text, lang, m, league)` returning resolved / ambiguous / elsewhere / unknown; `player_clarification` becomes one branch of it |
| `analyst/ask.py` | The "elsewhere" and "unknown" replies before any model call, with outcome `not_found` (EN / JA wording) |
| `analyst/tools.py` | `find_club(name)` beside `find_player`; both return `{"candidates": []}` for no match |
| `prompts/researcher.md` (v4) | "If a name in VIEWER_TEXT is not in PLAYERS or CLUBS, call find_player / find_club; if no candidates, reply `{"not_found": "<name as written>"}`" |
| `analyst/research.py` | Accept `not_found`; code checks the name really matches nobody before replying, so a model mistake cannot deny a real player |
| `analyst/verify.py` (backstop) | If the question contains a flagged unknown name, an Analyst answer that is not a not-found reply is rejected |
| Tests | Below |
| `docs/decisions.md` | ADR: deterministic name resolution before the model |

Not in scope: suggesting the closest real name ("did you mean Okafor?"). It would be useful,
but fuzzy matching invites new wrong identities; out of scope before the deadline.

## Tests and measurement

1. **Unit tests**: unknown01–03 shapes return `not_found` with no model call; every real player
   and club in either script, the referee, the venue and birthplaces never do; possessives,
   sentence-initial words, months ("January"), injections ("Ignore all previous
   instructions") and mixed scripts ("What is 伊藤健二's nationality?") never do.
2. **Offline false-positive check, free**: run the detector over every question in every saved
   dataset (90 cases, the original 38, extra-10, 37). Required: only unknown01–03 flagged, no
   other question flagged.
3. **Model check**: one complete 90-case run on `gpt-4.1-mini` (about ¥45). Required: unknown01–03
   correct; no case that passed in both baseline runs fails; no new false claim.
4. Card verifier catch rate unchanged (99.3 %).

## Effort and risk

About 2–3 hours including tests, plus scoring one run. Risk: a false "not found" on a real
question is worse than today's generic decline, so the detector is deliberately narrow (full-name
shapes only) and the offline check over all saved questions must find no false positive before
the model run.

## Review questions

1. Is the "known, not in tonight's squads" reply wanted, or should those stay as today?
2. Is the narrow rule (two capitalised words / katakana with "・") acceptable, accepting that a
   single unknown surname ("Vexford") still goes to the Researcher?
3. Feature freeze: build now (five days before the deadline), or record as the top post-demo
   item?
