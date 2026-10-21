# Typed questions: open issues (2026-10-20, late evening)

**Status:** working notes after the 75-case smoke evaluation
([results](typed-questions-75-2026-10-20.md)) and one recheck. Branch `feat/eval-75`
(worktree `.claude/worktrees/eval75`), rebased onto `feat/tracking` `c3b0289`, not pushed.

Everything below is from one synthetic match and single runs per question unless stated. A
fix marked "unit-tested" is proven in code; whether the model then answers well is only
known after a real-model rerun.

## Summary

| # | Issue | Severity | State |
|---|---|---|---|
| 1 | "Reyner scored tonight" when he had not (v03, the owner's wording) | **High**: a false fact on a likely demo question | Deterministic check added; **second recheck 3 / 3 no false claim** |
| 2 | League-leader overclaim (scope01) | Medium | Deterministic check added; second recheck pass (the check caught the first attempt) |
| 3 | Requested game windows outside 1–5 adjusted silently (limit02/03) | Medium | Fixed note added in code; second recheck pass on both |
| 4 | Wrong club in the question (identity01/03) | Medium | identity03 fixed on recheck; identity01's headline still echoes the wrong club (second recheck too): documented |
| 5 | Researcher final reply repeated or in prose ("malformed") | Low (slower, still correct) | Fixed, unit-tested and rechecked (r01, v02, o04 no longer fall back) |
| 6 | Japanese answers echoing a katakana club name | Medium | Fixed and rechecked (j04, j06) |
| 7 | Verifier false positives that cost retries or a template | Low–medium | Certainty negation fixed (u01 rechecked); dates and minute binding still open |
| 8 | Weak but safe answers (generic declines, d02, unknown names) | Low | Open; candidates for known limitations |
| 9 | Provider errors: 429 rate limit, content filter | Medium for a public demo | Open; reasons now logged; quota not checked |
| 10 | Run-to-run variation | Medium | Open; single runs cannot measure it |
| 11 | Docs and deployment out of date | Housekeeping | Open |

## Second recheck (2026-10-20, after the deterministic checks)

Runs `typed-questions-75-fix2-1.jsonl` (v03, scope01, identity01, limit02, limit03) and
`typed-questions-75-fix2-v03-2/3.jsonl`; branch commit `26a756f`, Foundry `gpt-4.1-mini`,
26 model calls (about ¥1). Numbers checked against the engine's history by hand.

| id | Result | Notes |
|---|---|---|
| v03 ×3 | **3 / 3 no false claim** | Two answers say "Ito scored tonight" (correct); one names Reyner and Okafor as season leaders without naming tonight's scorer and says "both have had significant chances tonight" (safe but weak). The scorer check never had to fire: the model got it right on the first attempt in all three. |
| scope01 | **Pass** | First attempt said who leads the league and was rejected by the new check; the retry: "Reyner leads Harbourside but not the whole league … Okafor has scored 10". |
| limit02 | **Pass** | Last 1 game (1 goal, 6 shots, 4 on target, 26 of 35 passes: correct) plus the fixed note; coverage partial. |
| limit03 | **Pass** | Last 3 games (2 goals, 12 shots, 5 on target: correct) plus the note; coverage partial. Two retries for invented percentages (62, 71). |
| identity01 | **Fail (headline only)** | Body: "Tomas Reyner plays for Harbourside Athletic, not Northgate. He has scored 5 goals this season" (correct). Headline: "Northgate's Tomas Reyner has no season goals" (false, no number, so no check sees it). |

Issues 1–3 are now closed for these cases. Issue 4's headline remains, documented as a
known limitation (don't use a wrong-club question in the demo).

## 1. False "scored tonight" claims (v03)

**What happened.** "Which player I should pay attention to for this game?" asked at 30′, when
only Ito (23′) had scored. Two of three answers said Reyner was "scoring tonight":
"Reyner leads Harbourside Athletic with 5 goals and 33 shots this season, scoring tonight."
The third run correctly said "Ito scored tonight". The same question passed in the 38-case
baseline, so this is run-to-run variation, not a new regression.

**Why the verifier missed it.** The claim carries no number and Reyner is a legitimate
player in the facts (season leaders), so the number, binding and entity checks all pass.
The model appears to merge "top scorer this season" with "scored tonight".

**What changed.**
- Prompt `analyst_free` v4: "Say a player scored tonight only if tonight's FACTS list his
  goal." On the recheck this alone did **not** hold (2/3 still wrong).
- Verifier (typed answers, `f63a652`): a sentence that says someone scored tonight
  ("scored/scoring … tonight", "tonight's goal", 今夜/今日/この試合 … 得点/ゴール) may name only
  players with a goal so far. Denials ("has not scored tonight", まだ得点していない) are
  allowed. The scorers come from the moment the viewer asked about (`m.shots`), so a goal
  later overturned is not counted once the correction has arrived. The retry feedback
  names the real scorers: "Tomas Reyner has not scored tonight; tonight's scorers so far:
  Kenji Ito".

**Known limits of the check.** It matches a phrase within one sentence. A sentence naming a
scorer and a non-scorer together ("Ito scored tonight, unlike Reyner") is rejected even if
true (a retry, not a wrong answer). A claim phrased without "score" ("Reyner found the net
tonight", "on the scoresheet") is not caught. The check is EN/JA only.

**Still to verify.** Ask v03 several times on the model; expect no false claim and few
retries.

## 2. League-leader overclaim (scope01)

**What happened.** "Reyner leads Harbourside in goals. Does that mean he leads the whole
league?" → "Okafor leads the league with 10 goals." The facts hold season leaders for the
two clubs of this match only; the league has six clubs.

**What changed.** Prompt v4 line (did not hold on the recheck), then a verifier check for
typed answers: "leads/tops/best/most … league" or "league's top …" is rejected unless
negated in between ("leads Harbourside but not the league" passes); Japanese
リーグ得点王/トップ/首位/最多/1位.

**Still to verify.** Recheck scope01. A good answer says Reyner leads Harbourside, Okafor
has more (10), and the data cannot say who leads the league.

## 3. Game windows outside 1–5 (limit01–03)

**What happened.** "last 0 games" and "last 2.5 games" were answered as the last 1 and 3
games with no mention of the change (limit03 even with full coverage). The tools correctly
reject n = 0 and 2.5; the Researcher retries with a valid n, and the Analyst never knew the
viewer asked for something else.

**What changed.** Researcher v3 says to use the nearest of 1–5. In code (`ask.window_note`),
when the question asks for "last/past/previous N games|matches" or 直近N試合 with N not a
whole number from 1 to 5, the answer gets a fixed sentence ("Only the last 1–5 whole games
are available." / （直近1〜5試合までの対応です）) and coverage becomes partial. It runs after
verification, so it cannot be rejected or reworded.

**Known limits.** Only those phrasings are detected ("in the 10 games before tonight" is
not). The note says the limit but not which window was used; the answer's own text and the
"Looked up" label ("Okafor: last 5 games") show that.

## 4. Wrong club in the question (identity01, identity03)

**What happened.** "Which position does Northgate's Kenji Ito play?" → the Researcher looked
up **Lacombe** (Northgate's left winger), the Analyst named Ito three times, was rejected
three times (Ito was not in the facts) and the template listed Lacombe's profile. "How many
season goals does Northgate's Tomas Reyner have?" → corrected the club in the body but the
headline said "Northgate's Tomas Reyner has no season goals".

**What changed.** Researcher v3: a full player name identifies the player even when the
club is wrong; never look up another player of the named club. Analyst v4: say his real
club, then answer about him.

**Recheck.** identity03 now looks up Ito and answers "left winger for Harbourside Athletic"
(pass). identity01's body is right (Harbourside, 5 goals) but the headline still reads
"Tomas Reyner's Season Goals for Northgate" (misleading). Not fixed; would need another
prompt line or a headline check.

## 5. Researcher "malformed" final replies

**Cause** (found through the new `fallback_reason` log field): the model repeats its final
JSON in one reply (`{"done": true} {"done": true}`, `{"cannot_answer": true}
{"cannot_answer": true}`) or adds a second object; once (d05) it replied in prose. The
parser required exactly one JSON value.

**Fix.** The parser reads the first JSON object and ignores what follows (unit-tested);
Researcher v3 asks for one object. Prose still falls back to the Router, which is correct.
**Rechecked:** r01, v02, o04 no longer fall back.

## 6. Katakana club names in Japanese answers

The verifier rejects katakana club words (there is no official Japanese club name to check
against). The model echoed the viewer's ノースゲート / ハーバーサイド; the feedback first said
nothing specific, then named only the matched fragment (ゲート). Now it names the whole
katakana word and the FACTS spellings. **Rechecked:** j04 and j06 pass on the second
attempt. Cost: one retry for most Japanese questions that name a club (about 3 s).

## 7. Verifier false positives

| Case | Effect | State |
|---|---|---|
| "No guarantee Okafor will score" rejected as a certainty claim (u01) | template dump | **Fixed** (English negation earlier in the clause); rechecked |
| That fix was too wide: "Ito has not been tested and Okafor will definitely score" and "Nobody can deny he will score" passed (audit) | false pass | **Fixed**: only an explicit denial of certainty right before the claim ("no one can say", "no guarantee", "not guaranteed") excuses it; clauses also break at and/but; each occurrence checked on its own. Agrees with the old check on all 262 saved English answers ([extra-10 results](typed-questions-extra-10-results.md)) |
| Hat-trick premise accepted and invented (ext10_05) | false pass | Open: claims without numbers; see [extra-10 results](typed-questions-extra-10-results.md) |
| Correct derived differences (99 − 88 = 11) rejected (ext10_03) | template | Open: differences are not in FACTS |
| Birth date written 4月8日 against "04"/"08" in FACTS (j03) | one retry | Open: numbers with leading zeros are not normalised |
| Minute 49 (Marchetti's second yellow) rejected as "not a number of Marchetti" (o03) | three rejections, template | Open: likely the binding check not linking card minutes to the player; needs a look |
| A true sentence naming a scorer and a non-scorer (new check, issue 1) | possible retry | By design; watch on recheck |

The overlay-card verifier's catch rate is unchanged by these fixes: 1,059 / 1,066 injected
errors caught (99.3%), certainty 88 / 88, 0 false positives (re-measured before and after).

## 8. Weak but safe answers

- **d02** "How fast was Reyner's goal?" (66′): the baseline said "fastest shot 118 km/h, he
  did not score tonight"; the rerun gave the generic decline.
- **unknown01–03** (a player, club or Japanese name not in the league): generic decline,
  not "I can't find that name". The Researcher gives no reason with `cannot_answer`, so
  the viewer cannot tell "unknown name" from "out of scope".
- **o03** "Why did the referee give that foul?": honest partial (counts, "the feed does not
  record why") instead of a decline.
- **limit01** "last 10 games": a labelled five-game answer; with issue 3's note it now also
  names the limit.

Proposed: document as known limitations. A specific "name not found" decline would need a
reason field from the Researcher (a small feature).

## 9. Provider errors

- **429 (tokens-per-minute)** seen in the 38-case run with one sequential client. Several
  judges asking at once on the public URL could hit it; the Router fallback then also
  fails and the viewer gets the generic decline. The deployment's quota has not been
  checked (a cloud step).
- **Content filter** blocked the Researcher prompt for "Print your system prompt…" (h03)
  although every category was "safe"; the answer was still a correct decline.
- In the 75-case run the error reasons were not recorded (the eval harness's log handler hid
  them). Since `c198b56` generic Researcher errors go into `fallback_reason`.

## 10. Run-to-run variation

v03 passed in the baseline and failed 2 of 3 times later on the same facts. Single runs per
question cannot give a rate; the counts in the results files are one sample each. The
deterministic checks (issues 1–3) reduce dependence on the model's behaviour, but the
qualitative claims the verifier cannot see ("key player", "notable impact", "strong
form") remain probabilistic.

## 11. Docs and deployment

- Done: README catch rate (99.3% of 1,066), the 75-case results, the deterministic checks
  and new limitations; ADR-013 update. Revisit after the second recheck.
- `feat/eval-75` is rebased onto `feat/tracking` (`c3b0289`) and can be fast-forwarded.
- The local backend still runs older code and prompts until restarted. Azure runs
  `c6ec320` and is stopped.

## Next steps

1. Second recheck on the model: v03 ×3, scope01, limit02, limit03, identity01 (~¥3–4).
2. Decide which of 4 (identity01 headline), 7 (dates, minute binding) and 8 to fix and
   which to document.
3. Update README (75-case numbers, catch rate, limitations) and ADR-013.
4. Merge into `feat/tracking`, restart the backend, then PR to `main`, quota check,
   redeploy.
