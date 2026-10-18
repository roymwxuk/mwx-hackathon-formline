# Milestone 6 (optional): team style baselines (tactics)

**Status:** ⬜ Not started, decision pending. Optional: starts only after the must-dos
(Foundry run for the Analyst comments, PR, Azure redeploy, video, submission) and only if
it can finish before Oct 24.
**Branch:** TBD
**Estimate:** about 12–18 h (half of it is redoing the demo assets after regeneration).
**Recorded:** 2026-10-18

## Why

The owner asked for a "team strategy analysis". The honest way to fit it into Formline
is the flagship idea applied to teams: **compare a team tonight with its own season norm**
("Northgate are pressing 8 m higher than usual"), the same way each shot is compared with
the shooter's own history. That keeps the pitch on one concept instead of adding a new
insight family.

Scope note: `CLAUDE.md` limits the project to personal baselines. Building this needs
ADR-012 in `docs/decisions.md` first (context, options, decision, why), recording that team
baselines are the same engine and concept, not a new feature family.

## Primer: football strategy as four questions

Coaches split a match into four phases. A team's strategy is its answer to each one.

| Phase | Question | Main styles (one end ↔ other end) |
|---|---|---|
| Out of possession | Where do we defend? | **Low block** ↔ **Mid block** ↔ **High press** |
| In possession | How do we move the ball? | **Possession (short passing)** ↔ **Direct (long balls)** |
| In possession | Where do we attack? | **Through the middle** ↔ **Down the wings** |
| Transitions | What happens the moment the ball changes hands? | **Counter-attack** (we win it) / **Counter-press** (we lose it) |

### The styles in plain words

1. **Low block ("park the bus")**: defence-heavy. Without the ball, all ten outfield
   players drop into their own half in two tight lines just outside their box. They don't
   chase; they block space and wait for mistakes. On the pitch: a compact rectangle of
   players in front of their own goal, opponents passing sideways in front of it.
2. **Mid block**: the default for most teams. Defend from around the halfway line, stay
   compact, press only when the ball enters their half.
3. **High press**: the opposite of the low block. Forwards chase the opposing defenders and
   goalkeeper near the opponent's goal to win the ball high up, where a turnover leads
   straight to a chance. On the pitch: many pressure events in the opponent's half, the
   defensive line near halfway.
4. **Possession play (short passing)**: keep the ball with many short, safe passes and
   move the opponent around until a gap opens. Long passing sequences, high completion,
   high possession share.
5. **Direct play (long ball)**: skip midfield with long forward passes to fast or tall
   forwards. Fewer passes per attack, more risk, quicker chances.
6. **Counter-attack**: defend deep, then the moment you win the ball sprint forward with
   2–4 quick passes into the space the opponent left behind.
7. **Counter-press (gegenpressing)**: the moment you lose the ball, swarm the player who
   has it to win it back within about 5 seconds.
8. **Wing play vs central play**: attack down the flanks and cross into the box, or combine
   through the middle.

Classic pairings:
- **Low block + counter-attack**: the underdog plan.
- **High press + possession + counter-press**: the dominant-team plan.
- **Mid block + direct play**: the pragmatic plan.

## How each style is measured

All are standard public metrics and computable from fields we already produce (events and
10 Hz tracking). Coordinates follow the documented pitch frame (0–100, attacking toward
x = 100).

| Style | Metric (plain meaning) | Source in our data |
|---|---|---|
| Low ↔ high block | **Defensive line height**: how far from their own goal the back four stand while the opponent has the ball (m) | tracking frames (`tracking/frames.py`) |
| Low ↔ high block | **Block depth**: deepest defender to highest forward, i.e. compactness (m) | `tracking/shape.py: depth_m()` |
| High press | **PPDA**: opponent passes allowed per defensive action in the opponent's 60% of the pitch; lower = more intense press | pass + pressure / tackle / interception events |
| High press | **Pressing height**: average distance up the pitch of the team's pressure events | pressure events |
| High press | **High turnovers**: balls won within 40 m of the opponent's goal | tackle / interception / possession_change x |
| Counter-press | Share of lost balls followed by a pressure within 5 s | `counterpress` flag on pressure events |
| Possession ↔ direct | **Possession %**, **passes per possession** | pass events + `possession` id |
| Possession ↔ direct | **Directness**: forward metres gained per metre passed; **long-ball share** (passes > 30 m) | pass start/end x, y |
| Counter-attack | **Fast breaks**: possessions won in the own half that reach a shot within 15 s | possession chains + shot events |
| Wings vs middle | **Attack lanes**: share of final-third entries in the left / centre / right lane | pass end_y in the final third |

## How to show it

1. **Style map** (the demo money shot): a small 2D chart, *x = where they defend*
   (low block ← → high press), *y = how they attack* (possession ↓ ↑ direct). Each team is a
   dot for **tonight**, a faded dot for **its season norm**, and an arrow between them.
2. **Block box on the pitch**: a translucent rectangle around the defending team's outfield
   players plus a dashed defensive-line marker. A low block visibly sits in front of goal.
3. **Lane bar**: three segments (left / centre / right), tonight vs norm.
4. **Verified Analyst comment at half-time and full-time**, e.g. "Harbourside sat in a low
   block (line 28 m from goal, season norm 37 m) and broke on the counter 4 times." Uses
   the existing facts pack → LLM → verifier path (`analyst/facts.py`, `analyst/verify.py`);
   numbers are model-free engine output, so the verifier checks every one.
5. **Casual vs analyst**: casual shows the style label and one sentence ("Defending deep
   tonight"); analyst adds the numbers (PPDA 14.2 vs norm 9.8).

## Reality check: what the synthetic data supports today

- **Every team currently plays the same way.** Players have stable styles, but team
  behaviour is one shared formula: pressure probability `0.12 + 0.24·x/100` for everyone
  (`generator/match_sim.py:292`), and one shared 4-3-3 shape and block parameters
  (`tracking/shape.py:34-36`). Measuring strategy now would show only random variation.
- **Real styles need a style profile per club in the generator**, so the engine can
  *recover* each team's style from the data, as it recovers each shooter's norm.
- **Cost:** changing the event generator re-randomises the demo match. The 88 Foundry
  cards (about ¥1–2 to redo), the Analyst comments, the golden personalization tests, the
  Jump-to moments, `docs/video-plan.md` and the screenshots all need redoing.

## Tasks

| # | Task | Estimate |
|---|---|---|
| T1 | ADR-012: team style baselines as the same concept; scope update in the roadmap | 0.5 h |
| T2 | Club style profiles in `generator/league.py`: two dials, **block height** and **directness**, distinct per club (e.g. one low-block/direct club, one high-press/possession club) | 1 h |
| T3 | Use the dials in `generator/match_sim.py` (pressure zones, pass length choice) and `tracking/shape.py` (out-of-possession push and depth per club) | 2–3 h |
| T4 | Team metrics + incremental team baselines next to `engine/baselines.py`, reusing `engine/shrinkage.py` (team prior = league average) | 2–3 h |
| T5 | Realism check in `docs/realism-report.md`: each club's measured style matches its profile across the history | 1 h |
| T6 | Regenerate; re-run Foundry overlays and Analyst comments; refresh goldens, Jump-to moments, video plan, screenshots | 3–4 h |
| T7 | Style map in the viewer (casual/analyst density, EN/JA) | 2–3 h |
| T8 | Half-time / full-time verified team comment (facts pack + verifier rules) | 1.5–2 h |

## Verification

- Realism: across the history, the low-block club's defensive line height and pressing
  height are clearly below the high-press club's; directness separates the direct club.
- Unit tests for each metric (PPDA, line height, directness, lanes) on hand-built events.
- Convergence: team baselines from the chaos stream equal those from the clean stream.
- Verifier: injected wrong team numbers and club names are caught, as for shot cards.
- Browser: the style map shows tonight vs norm for both clubs; the HT/FT comment appears.

## Open decisions (owner)

1. **When:** after the must-dos (recommended), now, or pitch-only ("next step" in the
   pitch and README, nothing built).
2. **First view:** style map (recommended), block box on the pitch, or Analyst comment only.
