# Formline architecture v2 — diagram generation brief

Create a clear architecture diagram from this description. This describes the repository implementation as inspected on October 20, 2026; it does not assert that every feature is already deployed. Preserve the existing architecture diagram and name new outputs `architecture-v2.svg` and `architecture-v2.png`.

## Purpose and visual direction

Formline turns a synthetic football match feed into explainable overlays, compares players with their own historical baselines, and lets two viewers see different insights at the same moment. It also answers questions using computed match facts.

Use a dark background with readable, high-contrast text. Suggested colors: green for deterministic code, purple for LLM roles, gold for browser interaction, and blue for Azure infrastructure. Use solid arrows for normal data flow and dashed arrows for recovery or supporting connections, with explicit labels. Do not rely on color alone.

Prefer two figures: a simple 16:9 overview suitable for a short demo video, plus a detailed agent-flow figure. Avoid squeezing every implementation detail into one image. Use the exact node labels below where practical.

## Figure 1: system overview

Arrange the main data flow from left to right. Use separate boundaries for **preparation**, **Azure hosting**, **viewer browser**, and **external services**.

### A. Preparation: synthetic data and generated artifacts

This is a preparation step, not an always-running Azure service.

- **Seeded synthetic football data**: fictional clubs and players, historical matches, one demo match, and synthetic player/ball tracking derived from events.
- **History baseline preparation**: builds historical player statistics and the priors used by the baseline engine.
- **Precompute demo output**: runs the engine and agent workflows to save overlay cards, Analyst comments, and follow-up answers.
- **Saved artifacts**: feed files, tracking files, historical facts, generated overlays/comments/answers, and model-response cache. These are file-based artifacts; do not draw a deployed database or object-storage service.

Show preparation supplying artifacts to the backend. Precomputation can call Foundry; serving an already generated card does not require regenerating its text.

### B. Azure Container Apps environment

Label the environment **Japan East · consumption · minimum 0 replicas**. Draw two distinct applications inside it.

**formline-api — Python / FastAPI / Microsoft Agent Framework**

Show three functional areas, rather than implying that every viewer request traverses every agent:

1. **Default replay**: merges the saved match feed, precomputed overlay cards, and saved Analyst comments into a paced SSE stream. Tracking frames accompany playback. Label this path **default: saved output**.
2. **Live generation / chaos replay**: processes feed events through the deterministic engine and agent workflows during replay. Label this path **optional: `live=true`**. Chaos replay injects duplicates, delays, out-of-order events, and corrections, and implies live processing.
3. **Question API**: accepts follow-up chip requests and typed questions, retrieves facts as of the viewer's event/version, and returns checked answers or an explicit clarification/decline/fallback.

Both replay modes feed the same **SSE output** node. SSE carries match events, overlay cards, Analyst comments, and tracking frames. Event messages support reconnect/resume using `Last-Event-ID`; transient tracking/clock frames do not have event IDs.

**formline-web — Next.js**

Label this **serves viewer application**. Draw an arrow to the browser labeled **web assets / application**. Do not put the actual browser rendering and interactive filtering inside the Azure container boundary.

The browser connects directly to the backend for the SSE stream and question requests. Do not imply that the Next.js container proxies those calls.

### C. Viewer browser

Draw a browser containing:

- **2D pitch and synchronized overlays**: player/ball animation, timed cards, goal/set-piece labels, and VAR correction notices.
- **Personalization**: EN/JA, casual/analyst, favorite clubs and players, player focus strip, and “my metric” filter. Favorites affect card priority; settings affect the selected content and its presentation.
- **Match Analyst panel**: comments, follow-up chips, typed questions, and answers.
- **Two-viewer comparison**: two views of the same match moment with different settings.

Connect backend → browser with **SSE: events + cards + comments + tracking**. Connect browser → backend with **POST `/matches/{id}/ask`** and **POST `/matches/{id}/ask/free`**. Response arrows carry answers. Abbreviated `/ask` and `/ask/free` labels are acceptable if the full paths appear in a caption.

### D. External services and delivery

Draw these outside the Container Apps environment:

- **Microsoft Foundry — gpt-4.1-mini deployment**. LLM roles in the backend use it through Microsoft Agent Framework. The deployed backend authenticates with its managed identity and the **Foundry User** role; no API key is required for that deployed path. Draw model calls from LLM roles, not from the deterministic verifier or browser. Preparation may also use Foundry with developer credentials.
- **Log Analytics**: receives container console logs from both hosted applications. This is operational logging, not an LLM evaluator.
- **GitHub Actions → GHCR → Azure Container Apps**: CI validates and builds images; pushes to `main` publish Linux/amd64 backend and frontend images tagged with commit SHA and `latest`. An explicit **`deploy.sh <image tag>`** operation creates or updates the Container Apps using those images. Publishing an image does not automatically deploy it. Show `deploy.sh` controlling the Azure update and Azure pulling images from GHCR; GHCR does not execute the script.

Keep cost controls in a small caption: **scale to zero · response cache · model-call budgets · ingress can be disabled manually**. Do not imply that ingress automatically switches off when idle. Omit cumulative cost estimates and billing claims.

## Figure 2: engine and agent detail

Use two lanes: proactive match overlays and interactive questions. Distinguish LLM decisions/writing from deterministic checks and data retrieval.

### Lane 1: proactive overlay generation

Show this flow, used during precomputation and optional live replay:

```text
Synthetic feed
  → Event ingestion and append-only log
  → Deterministic statistics and personal baselines
  → Insight detectors
  → Insight Selector
  → Narrators for EN/JA × casual/analyst
  → Deterministic Verifier
  → Overlay Composer
  → Saved overlay artifacts OR live SSE output
```

Explain these nodes concisely:

- **Ingestion [code]**: event-ID deduplication, event-time reorder window, and corrections/retractions.
- **Statistics and baselines [code]**: shot speed, placement, and finish quality compared with the shooter's own history; conditional comparisons by zone/body part/pressure; wider buckets for sparse history; empirical Bayes shrinkage. Derived state can be rebuilt from the log.
- **Insight detectors [code]**: identify salient deviations from personal norms; attach source event IDs. Corrections roll back affected baseline updates and retract or replace dependent overlays. Show a correction path back into derived state, not only a new narrative.
- **Insight Selector [rules + LLM]**: deterministic shortlist and priorities, then model selection with rule fallback.
- **Narrators [LLM]**: four language/audience variants: EN casual, EN analyst, JA casual, JA analyst. These are workflow roles/variants, not four separately deployed model services.
- **Verifier [code; no LLM call]**: checks structure, allowed numbers/entities, estimate wording, certainty phrases, and presentation constraints. It is a guardrail, not proof that arbitrary prose is correct or relevant.
- **Overlay Composer [code]**: fills a fixed template catalog and includes timing, priority, audience, language, and source-event lineage.

Label orchestration **Microsoft Agent Framework WorkflowBuilder · shared state · explicit handoffs**.

Draw verifier rejection → the corresponding Narrator as **retry with feedback**. After three failed attempts, draw **deterministic template fallback → Overlay Composer**. Bad JSON and model failures also enter recovery. Do not write “never wrong,” “guaranteed accurate,” or “100% verified.”

Alongside this lane, show **Match Analyst [LLM + code checks]** producing comments at key moments such as shots, corners, cards, and VAR. Its comments enter saved artifacts or the live stream. **Question Suggester [LLM]** chooses 2–3 applicable questions from a fixed catalog, with code validation and a deterministic default order on failure. The number available can limit the number selected.

### Lane 2: interactive question answering

Draw two entry paths:

**Follow-up chip — `/ask`**

```text
Browser's selected catalog question + comment reference
  → Validate request and recover the referenced match moment
  → Saved answer, if available
       OR computed facts → Analyst → deterministic answer verifier
  → Answer / retry / template fallback
```

**Typed question — `/ask/free`**

```text
Question + latest received event ID/version + language
  → Input/rate-limit checks and identity clarification when needed
  → Researcher [LLM]
       ↔ Read-only fact tools [code; validated arguments]
  → Retrieved evidence
  → Analyst [LLM]
  → Deterministic answer verifier [code]
  → Answer with coverage / clarification / decline / fallback
```

The Researcher selects and chains tools; it does not write the viewer-facing answer. Tool results come from computed synthetic match/history facts. Examples include current player/team statistics, biographies, season leaders, and recent-game history. Repeated lookups retain their distinct tool arguments. Retrieval is structured fact lookup, not vector search or web search.

Show **Researcher failure / timeout / unavailable budget → Router [LLM fallback] → validated fact-section retrieval → Analyst**. The Router is an alternative retrieval strategy, not an additional mandatory step after successful research.

Show the Analyst's reject → retry path and terminal template/rephrase fallback without implying that every answer succeeds. Clarification and decline can terminate before answer generation. Label shared controls **model/tool-call limits · overall deadline · read-only tools · event-time boundary**. Do not imply that a rejected question necessarily calls a model.

The typed-question verifier checks against retrieved facts and includes some targeted attribution checks; its coverage is incomplete. Do not depict another LLM as the verifier or claim full semantic truth checking.

## Corrections to the original diagram

1. Replace “A card is never blocked, and never wrong” with **“Retries, then deterministic template fallback.”**
2. Explicitly distinguish default saved-output replay from optional live agent execution.
3. Add the full typed-question path and Router recovery path; keep it separate from follow-up chips.
4. Update “Suggester: 2 of 4 questions” to **“2–3 applicable catalog questions.”**
5. Move viewer rendering and interactive personalization into the browser boundary.
6. Separate GHCR image publication from the explicit Azure deployment operation.
7. Remove stale cumulative token-cost estimates and absolute correctness claims.
8. Avoid presenting the mutation-test catch rate as real-answer accuracy; omit evaluation percentages from the architecture drawing.

## Output request to diagram generator

Generate an uncluttered overview and, if possible, a second detailed flow diagram following this brief. Prioritize readable text and accurate boundaries over decorative icons. Supply editable SVG plus high-resolution PNG. Do not invent extra services such as PostgreSQL, Redis, a vector database, Kubernetes, a message broker, or Azure Container Registry. The project currently publishes images to GHCR.
