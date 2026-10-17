# Demo artefacts

`overlays/<match_id>.jsonl` (optional): overlays precomputed with Microsoft Foundry
(`uv run formline-gen overlays` with `AZURE_AI_PROJECT_ENDPOINT` set). When present, the
container serves them instead of the fake-model overlays built into the image, so the
deployed demo shows real LLM narration without calling the model on every cold start.
