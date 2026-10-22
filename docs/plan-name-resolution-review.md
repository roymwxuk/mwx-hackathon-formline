# Name-resolution plan: review and suggested revisions

Prepared 2026-10-22 by Codex. Reviewed `docs/plan-name-resolution.md` and the current Router, Researcher, tool and answer paths in Claude's `worktree-fix-negation-extra10` checkout at `0d9d873`. This is a design review, not implementation or a model evaluation. Examples below are proposed tests, not reproduced failures of an implemented resolver.

The proposed pre-model name resolution addresses a real failure class: attaching a known player's facts to an unknown identity. Keep the fix narrow. Capitalisation and punctuation identify possible names; they do not establish that a phrase names a person or club.

## 1. Reduce false positives when detecting names

Use **name-shaped text plus contextual evidence**, with an unresolved state when confidence is insufficient.

Suggested sequence:

1. Resolve known full-name spans and aliases using boundaries, preserving their source offsets and the existing ambiguity behaviour. Use longest matches first. Do not remove a known surname inside an otherwise unrecognised full-name span and thereby silently resolve a different identity.
2. Extract remaining candidate spans using English capitalisation or Japanese katakana patterns. These are candidates, not automatic `unknown` decisions.
3. Require a narrow contextual cue before returning a deterministic not-found reply: for example, a possessive full name followed by nationality/birthday, an explicit phrase such as "player named …", or a club-shaped phrase used as the subject of a recent-match question. Define each supported pattern explicitly rather than treating all surrounding football language as sufficient evidence.
4. Exclude established football terms and ordinary phrases, such as "Shot Speed", "Expected Goals", and 「パス・シュート」. Vocabulary exclusions are supplementary: no finite list covers all ordinary text.
5. If a candidate lacks sufficient evidence, return `unresolved` and continue to the Researcher. Never interpret this state as proof that a name exists.

Do not blindly discard the first word of every sentence: "Milo Vexford's nationality?" starts with the requested name. Exclude grammatical lead-ins such as "Who" or "Compare" only when the parser can distinguish them from the candidate span. Strip possessives for lookup while retaining the original span for display.

| Proposed test | Required outcome |
|---|---|
| "What is Milo Vexford's nationality?" | Unknown person; deterministic not-found reply |
| "Milo Vexford's nationality?" | Same result despite sentence-initial name |
| "How did Ashfen Wanderers do in their last game?" | Unknown club if the supported club-context rule establishes it; otherwise unresolved lookup path |
| "Compare Shot Speed" / "Explain Expected Goals" | No name-based rejection |
| 「パス・シュートを比較して」 | No name-based rejection |
| "Tell me about Silver Meadows" | Unresolved unless a supported contextual rule establishes an entity request |
| Known names in lowercase, possessive form or mixed scripts | Preserve supported known-name behaviour |
| "Milo Okafor" | Do not silently substitute Daniel Okafor based on the surname |

The conservative rules intentionally miss some unknown names. Measure false positives and misses separately; do not describe the detector as complete name recognition.

## 2. Bind model-returned `not_found` to the question and actual lookup evidence

The proposed check that a model-returned string matches nobody is insufficient. A model could return an arbitrary unknown name absent from an otherwise valid question and cause an incorrect rejection.

Suggested contract:

- Preserve the exact viewer-text span for each candidate, with a stable span ID or offsets. Normalisation for lookup must be explicit and shared by code and tools.
- A Researcher `not_found` result must identify that candidate, its entity type, and a corresponding lookup record. Code must confirm the candidate occurs in the effective question passed to the model; do not accept an unrelated invented name.
- Require an admitted, validated `find_player` or `find_club` call for that same candidate with an empty result. A tool error, timeout or call-limit response is not an empty result.
- Distinguish "not in this match's squads" from "absent from the league registry". A squad-only empty search cannot establish league-wide absence. Check the wider registry when necessary to classify `elsewhere`.
- Validate the final reply as an explicit variant: `done`, `cannot_answer`, or `not_found`. Reject contradictory combinations. Malformed or unsupported not-found claims should follow bounded existing recovery, not become a user-visible assertion.
- Keep lookup admission, model budgets and the request deadline in force. The pre-model high-confidence path still needs no model call; only the uncertain Researcher path requires lookup evidence.

Tests should cover a fabricated returned name absent from the question; an empty lookup for a different name; a nonempty lookup followed by `not_found`; a tool failure presented as an empty result; a player known elsewhere; conflicting final keys; and truncation/normalisation at the existing question-length boundary.

## 3. Specify multiple-name handling and preserve identity bindings

Return a collection of entity mentions, not one whole-question classification. Each mention should retain its source span, possible IDs, entity type, resolution status and evidence. Resolve all relevant mentions before choosing the response policy.

Suggested policy for the deadline:

| Mentions in the request | Response policy |
|---|---|
| All resolved and supported | Continue with their explicit IDs |
| Ambiguous requested entity | Ask for clarification; never choose an identity arbitrarily |
| Unknown entity required for a comparison | Identify the missing name and ask for correction; do not imply the comparison was answered |
| Independent requests, one supported and one unknown | Prefer a deterministic correction request for the first release; if partial answers are supported, explicitly mark the missing part and preserve coverage metadata |
| Uncertain candidate | Continue to validated lookup, not automatic rejection |

For "Compare Milo Vexford with Okafor", do not return Okafor's numbers under the unknown name or label an Okafor-only answer as a complete comparison. If the product wants partial answers, make that an explicit policy with tests rather than an accidental fallback.

Add tests for two known players; known plus unknown in both orders; two unknown names; a known full name plus an ambiguous surname; full-name mismatch sharing a known surname; repeated aliases of one player; and mixed English/Japanese mentions. Preserve existing full-name and club-qualified disambiguation tests.

The proposed verifier backstop should consume the same structured resolution result as the request handler, not independently rediscover names with another regex. Document its limit: it prevents known flagged unknown-identity requests from receiving attributed facts; it does not prove arbitrary answer identities are correct.

## 4. Separate an out-of-match target from a valid historical reference

A known club outside tonight's match is not inherently an invalid mention. Historical fact packs already contain previous opponents. Rejecting every `elsewhere` mention would block supported questions.

Suggested distinction:

- **Requested target:** "How did Elderwick Town do in its last three games?" asks for an out-of-match club's own history. If the current tool contract cannot answer, explain that scope restriction; do not call the club unknown.
- **Historical filter/reference:** "How did Okafor play against Harbourside in his last three games?" asks about a supported player and a historical opponent. Permit it when the available history supports it. The same principle applies to another known league club outside tonight's fixture.
- **Identity context:** a birthplace, nationality, referee or venue mention is not automatically a player/club target. Being allow-listed prevents an unknown-name flag; it does not grant unsupported retrieval capability.
- **Uncertain role:** do not terminate just because an out-of-match name occurs. Let the Researcher inspect supported history under existing tool validation and scope rules.

Build the historical-opponent regression tests from actual saved player/team history: select a known opponent outside tonight's fixture, ask about the supported player's recorded game against it, and require no early `elsewhere` rejection. Also test the same club as the direct target of an unsupported request and mixed supported/unsupported targets. Keep current match-scoped tool restrictions unless separately authorised to expand them.

## Implementation and evaluation handoff

The plan names `analyst/research.py`; the existing module is `analyst/researcher.py`. Update the intended result type, parsing, `answer_free` handling, logging and fake-tool fixtures together. Reuse the existing `declined` message field if introducing an outcome such as `not_found`, and verify client rendering and evaluation categorisation.

Before a model run:

1. Freeze expected outcomes for the positive, negative, mixed-entity and historical-reference tests above.
2. Run the resolver offline over the existing saved questions, while explicitly declaring how new `elsewhere` outcomes should be counted. The current requirement that "only unknown01–03" be flagged must distinguish unknown detections from any intentionally added out-of-match outcomes.
3. Assert zero model calls for deterministic decisions and unchanged budget/timeout behaviour for unresolved lookup paths.
4. Preserve prior datasets and outputs. On an authorised rerun, score relevance, grounding and not-found behaviour separately. Do not treat a correct not-found message as proof that all unsupported identities are caught.

Claude remains responsible for implementation. This review adds no authorisation for model/cloud calls and makes no claim about current deployment status.
