#!/bin/sh
# Container entrypoint. If overlays precomputed with Microsoft Foundry are shipped in
# demo/overlays/, they replace the image's fake-model overlays, so the deployed demo shows
# real LLM narration without calling the model on every cold start.
set -e
if ls demo/overlays/*.jsonl >/dev/null 2>&1; then
  mkdir -p "$DATA_DIR/overlays"
  cp demo/overlays/*.jsonl "$DATA_DIR/overlays/"
  echo "using precomputed overlays from demo/overlays"
fi
if ls demo/analyst/*.jsonl >/dev/null 2>&1; then
  mkdir -p "$DATA_DIR/analyst"
  cp demo/analyst/*.jsonl "$DATA_DIR/analyst/"
  echo "using precomputed Analyst comments from demo/analyst"
fi
exec uvicorn formline.api:app --host 0.0.0.0 --port "${PORT:-8000}"
