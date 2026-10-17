#!/usr/bin/env bash
# Re-enable public ingress for both apps (after stop.sh). Same URLs as before.
set -euo pipefail
source "$(dirname "$0")/common.sh"
az containerapp ingress enable -n "$API" -g "$RG" --type external --target-port 8000 -o none
az containerapp ingress enable -n "$WEB" -g "$RG" --type external --target-port 3000 -o none
DOMAIN=$(az containerapp env show -n "$ENV_NAME" -g "$RG" --query properties.defaultDomain -o tsv)
echo "started: https://$WEB.$DOMAIN (viewer), https://$API.$DOMAIN (backend)"
