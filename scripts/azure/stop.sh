#!/usr/bin/env bash
# Stop both apps completely: disable public ingress so nothing (users or bots) can wake them.
# They already scale to zero when idle; this also prevents wake-ups. Undo with start.sh.
set -euo pipefail
source "$(dirname "$0")/common.sh"
for app in "$API" "$WEB"; do
  az containerapp ingress disable -n "$app" -g "$RG" -o none
  echo "stopped: $app (ingress disabled)"
done
