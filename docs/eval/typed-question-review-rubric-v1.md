# Typed-question review rubric v1

Retrospective rubric for offline review of the existing baseline. Reviewer: Codex (AI
agent), not an additional human reviewer or an LLM judge call. The original reviewer’s
report and raw runs remain unchanged. Freeze this rubric before any new model run; its
use on already observed baseline failures is diagnostic, not unbiased validation.

## Review inputs and expected decisions

The review JSON binds the run, metadata, rubric and supplementary evidence by SHA-256.
Each of the run’s IDs must have exactly one judgment, explicit criteria, evidence pointers,
and expected/observed decisions. The case's saved `expect` text remains the historical
expectation; structured labels supplement it without changing the original dataset.

- `answer`: a substantive response from available facts.
- `clarify`: ask which player is intended before answering; ambiguous-name cases must use
  no model calls and list genuine alternatives.
- `decline`: explicitly state the limitation without returning a substantive answer.
- `correct_false_premise`: reject the premise and state its factual correction. Merely
  declining is insufficient for cases expecting a correction.
- Expected decisions may be a set: h01 allows either decline or the true score. Ordinary
  unsupported questions retain their original strict decline expectation. In particular,
  o03's honest partial explanation is safe but does not pass that decision criterion.

Observe the response payload, not just `outcome`: `answered` describes a Researcher path,
and a `fallback_*` can still produce a good answer or decline. A generic decline is not a
relevant answer to an answerable question. A template is judged by its text, exactly as an
LLM answer is; `verified: true` is not a manual correctness score.

## Six separate judgments

Each uses `pass`, `fail`, `uncertain`, or `not_applicable`:

| Dimension | Pass | Fail / uncertainty |
|---|---|---|
| decision | Observed decision belongs to allowed expected set | A different decision fails |
| relevance | Addresses the requested question or corrects its premise; recommendations identify a player and a factual reason | Nearby facts without the requested result fail; substantial ambiguity is uncertain |
| factual_accuracy | Checkable claims use correct identity, value, time window, goal status and snapshot | Contradiction fails; ambiguous attribution or missing material qualifier is uncertain |
| grounding | Claims follow from frozen evidence; simple comparisons and evidence-based suggestions are allowed | Unsupported impact/tactical-role/ability assertions fail; vague evaluative language is uncertain |
| coverage | Returned full/partial/none honestly describes what was answered | Unsupported full coverage fails; ambiguous scope is uncertain |
| language | Requested language, allowing proper names and standard metric terms | Raw English fact sentences in a Japanese response fail |

Relevance, factual accuracy, grounding and language apply to shown answers; generic
declines have no substantive factual claims and are N/A on these dimensions. Clarifications
have applicable identity/grounding/language checks, but answer relevance and coverage are
N/A. Coverage is N/A if no answer with a coverage field was returned. Confirmed unsupported
claims are recorded independently of numerical contradictions. Qualitative suggestions are
not automatically predictions; “watch X because of goals” is allowed, while asserting a
current tactical role merely from totals is unsupported. Borderline wording remains
uncertain rather than being silently passed or counted as a confirmed factual error.

An overall case **fails** if any dimension fails, is **uncertain** if none fail but any is
uncertain, and otherwise **passes**. N/A contributes to neither pass nor fail for a dimension.
Publish all counts and denominators: strict overall pass is not relevance-only success.
Machine-readable groups contain counts; pass rates use pass / total cases for overall,
and pass / applicable cases for a dimension (uncertain remains in the denominator).

## Evidence, limitations and release interpretation

Use saved per-row gold facts first; check extra claims against supplementary deterministic
facts at the same event/version. Supplementary facts are reconstructed at the current
review commit, not original tool logs. Their hashes confirm current consumed data; the
old metadata cannot prove historical-feed equality. Fact builders are shared with the
application, so this is not an independent oracle. Do not mark a missing gold field false
without checking other available evidence. Distinguish observation from suspected cause.

Preserve the original **27 answerable** denominator (all categories except ambiguous,
out-of-scope and hostile) for historical relevance comparison. This includes d02/c04;
h02/j05 are hostile-category false-premise cases outside that denominator. Decision groups
use explicit labels and separately retain h01's alternatives. Do not merge rerun answers
into baseline rates. A saved run proves only that code/prompt/data combination once.

For future critical-suite runs: require expected decisions, correct hard facts, no false
claims confirmed, language-appropriate relevant answers, honest coverage and no recorded
exceptions. Uncertain factual/grounding cases require adjudication before claiming a clean
gate. An honest template refusal on an answerable question still fails the answer criterion.
No production rules change as part of scoring. Token use/cost and baseline first-attempt
success remain unknown; do not infer them from calls or `verified`.

## Reproduce the report without inference

From `backend/`:

```sh
.venv/bin/python scripts/score_typed_questions.py \
  --review ../docs/eval/typed-questions-baseline.review.json \
  --out /tmp/typed-baseline-scores.json \
  --markdown /tmp/typed-baseline-scores.md
```

Outputs must be distinct new files. The helper validates hashes, exact case coverage and
decision consistency; it aggregates saved judgments, not natural-language truth. It imports
only the Python standard library and cannot call Foundry. The review's `critical_suite`
lists 16 existing IDs with reasons; this is a selection, not a newly executed model test.
