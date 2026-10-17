#!/usr/bin/env bash
# Provision Microsoft Foundry for Formline: resource group, AI Services resource, Foundry
# project, small model deployment, and data-plane roles for the signed-in user. Idempotent:
# re-running skips what already exists. Writes the endpoint into backend/.env (gitignored).
#
# Usage: scripts/azure/provision.sh        (override any variable below via the environment)
set -euo pipefail
export PYTHONWARNINGS=ignore

RG=${RG:-formline-rg}
LOC=${LOC:-japaneast}
AI=${AI:-formline-ai-mwx}            # globally unique: also the custom subdomain
PROJECT=${PROJECT:-formline}
MODEL=${MODEL:-gpt-4.1-mini}
MODEL_VERSION=${MODEL_VERSION:-2025-04-14}
DEPLOYMENT=${DEPLOYMENT:-$MODEL}
CAPACITY=${CAPACITY:-50}             # thousands of tokens per minute (a rate limit, not a charge)
ROLES=("Cognitive Services OpenAI User" "Azure AI Developer")

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
echo "subscription: $(az account show --query name -o tsv)"

az group create -n "$RG" -l "$LOC" -o none
echo "resource group: $RG ($LOC)"

if ! az cognitiveservices account show -n "$AI" -g "$RG" -o none 2>/dev/null; then
  az cognitiveservices account create -n "$AI" -g "$RG" -l "$LOC" --kind AIServices --sku S0 \
    --custom-domain "$AI" --allow-project-management --assign-identity --yes -o none
fi
echo "AI Services resource: $AI"

if ! az cognitiveservices account project show -n "$AI" -g "$RG" --project-name "$PROJECT" -o none 2>/dev/null; then
  az cognitiveservices account project create -n "$AI" -g "$RG" -l "$LOC" --project-name "$PROJECT" -o none
fi
echo "Foundry project: $PROJECT"

if ! az cognitiveservices account deployment show -n "$AI" -g "$RG" --deployment-name "$DEPLOYMENT" -o none 2>/dev/null; then
  az cognitiveservices account deployment create -n "$AI" -g "$RG" --deployment-name "$DEPLOYMENT" \
    --model-name "$MODEL" --model-version "$MODEL_VERSION" --model-format OpenAI \
    --sku-name GlobalStandard --sku-capacity "$CAPACITY" -o none
fi
echo "model deployment: $DEPLOYMENT ($MODEL $MODEL_VERSION, GlobalStandard, ${CAPACITY}k TPM)"

SCOPE=$(az cognitiveservices account show -n "$AI" -g "$RG" --query id -o tsv)
ME=$(az ad signed-in-user show --query id -o tsv)
for role in "${ROLES[@]}"; do
  if [ -z "$(az role assignment list --assignee "$ME" --role "$role" --scope "$SCOPE" --query '[0].id' -o tsv)" ]; then
    az role assignment create --assignee-object-id "$ME" --assignee-principal-type User \
      --role "$role" --scope "$SCOPE" -o none
  fi
  echo "role for you: $role"
done

ENDPOINT="https://$AI.services.ai.azure.com/api/projects/$PROJECT"
ENV_FILE="$ROOT/backend/.env"
[ -f "$ENV_FILE" ] || cp "$ROOT/backend/.env.example" "$ENV_FILE"
python3 - "$ENV_FILE" "$ENDPOINT" "$DEPLOYMENT" <<'PY'
import sys, pathlib
path, endpoint, deployment = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
lines = path.read_text().splitlines()
values = {"AZURE_AI_PROJECT_ENDPOINT": endpoint, "AZURE_AI_MODEL_DEPLOYMENT_NAME": deployment}
out, seen = [], set()
for line in lines:
    key = line.split("=", 1)[0].strip()
    if key in values:
        out.append(f"{key}={values[key]}"); seen.add(key)
    else:
        out.append(line)
out += [f"{k}={v}" for k, v in values.items() if k not in seen]
path.write_text("\n".join(out) + "\n")
PY
echo "wrote backend/.env: endpoint=$ENDPOINT deployment=$DEPLOYMENT"
