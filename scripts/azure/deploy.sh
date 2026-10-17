#!/usr/bin/env bash
# Deploy (create or update) the backend and viewer to Azure Container Apps from the images
# CI published to GHCR. Both apps scale to zero when idle. The backend's managed identity
# gets "Foundry User" on the Foundry resource, so live narration needs no keys.
#
# Usage: scripts/azure/deploy.sh <image tag>   (the commit SHA CI published, e.g. origin/main)
set -euo pipefail
source "$(dirname "$0")/common.sh"
TAG=${1:?usage: deploy.sh <image tag>}

DOMAIN=$(az containerapp env show -n "$ENV_NAME" -g "$RG" --query properties.defaultDomain -o tsv)
API_IMG="ghcr.io/$OWNER/formline-backend:$TAG"
WEB_IMG="ghcr.io/$OWNER/formline-frontend:$TAG"
ENV_VARS=(
  "CORS_ORIGINS=[\"https://$WEB.$DOMAIN\"]"
  "AZURE_AI_PROJECT_ENDPOINT=https://$AI.services.ai.azure.com/api/projects/$PROJECT"
  "AZURE_AI_MODEL_DEPLOYMENT_NAME=$DEPLOYMENT"
  "SIM_SPEED=20"
)

if az containerapp show -n "$API" -g "$RG" -o none 2>/dev/null; then
  az containerapp update -n "$API" -g "$RG" --image "$API_IMG" --set-env-vars "${ENV_VARS[@]}" -o none
else
  az containerapp create -n "$API" -g "$RG" --environment "$ENV_NAME" --image "$API_IMG" \
    --target-port 8000 --ingress external --cpu 0.5 --memory 1.0Gi \
    --min-replicas 0 --max-replicas 1 --system-assigned --env-vars "${ENV_VARS[@]}" -o none
fi
echo "backend: https://$API.$DOMAIN  ($API_IMG)"

PRINCIPAL=$(az containerapp show -n "$API" -g "$RG" --query identity.principalId -o tsv)
SCOPE=$(az cognitiveservices account show -n "$AI" -g "$RG" --query id -o tsv)
if [ -z "$(az role assignment list --assignee "$PRINCIPAL" --role "Foundry User" --scope "$SCOPE" --query '[0].id' -o tsv)" ]; then
  az role assignment create --assignee-object-id "$PRINCIPAL" --assignee-principal-type ServicePrincipal \
    --role "Foundry User" --scope "$SCOPE" -o none
fi
echo "backend identity: Foundry User on $AI"

if az containerapp show -n "$WEB" -g "$RG" -o none 2>/dev/null; then
  az containerapp update -n "$WEB" -g "$RG" --image "$WEB_IMG" -o none
else
  az containerapp create -n "$WEB" -g "$RG" --environment "$ENV_NAME" --image "$WEB_IMG" \
    --target-port 3000 --ingress external --cpu 0.25 --memory 0.5Gi \
    --min-replicas 0 --max-replicas 1 -o none
fi
echo "viewer:  https://$WEB.$DOMAIN  ($WEB_IMG)"
