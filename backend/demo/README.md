# Demo artefacts

`analyst/<match_id>.jsonl` and `analyst/<match_id>.answers.jsonl` (optional): the Match
Analyst's comments with their suggested follow-up questions, and the answers to those
questions, precomputed with Microsoft Foundry (`uv run formline-gen analyst` with
`AZURE_AI_PROJECT_ENDPOINT` set). When present they replace the fake-model ones built into
the image; `/ask` serves the precomputed answers and calls the model only for anything else.

`overlays/<match_id>.jsonl` (optional): overlays precomputed with Microsoft Foundry
(`uv run formline-gen overlays` with `AZURE_AI_PROJECT_ENDPOINT` set). When present, the
container serves them instead of the fake-model overlays built into the image, so the
deployed demo shows real LLM narration without calling the model on every cold start.

**Shipped:** `overlays/mtc_s26_md11_har_nor.jsonl`: the live match narrated by `gpt-4.1-mini` on
Microsoft Foundry (prompt version v3, 2026-10-17): 64 overlays (56 cards, 4 VAR corrections,
4 banners); all 60 card texts written by the model and passed by the verifier, 0 template
fallbacks, 70 model calls (about ¥8).
