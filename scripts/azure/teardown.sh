#!/usr/bin/env bash
# Delete everything Formline created in Azure: the resource group (Container Apps, their
# environment and Log Analytics workspace, the Foundry resource, project and model
# deployment, role assignments on them) and the subscription budget. Irreversible.
# The GHCR images and the GitHub repository are not touched.
#
# Usage: scripts/azure/teardown.sh          (asks for the resource group name to confirm)
set -euo pipefail
source "$(dirname "$0")/common.sh"
BUDGET=${BUDGET:-formline-budget}

echo "subscription: $(az account show --query name -o tsv)"
echo "This permanently deletes resource group '$RG' and budget '$BUDGET'."
read -r -p "Type the resource group name to confirm: " answer
[ "$answer" = "$RG" ] || { echo "aborted"; exit 1; }

if az group show -n "$RG" -o none 2>/dev/null; then
  az group delete -n "$RG" --yes -o none
  echo "deleted: resource group $RG"
else
  echo "resource group $RG not found, skipping"
fi

# Deleting an AI Services resource only soft-deletes it; purge it so the name is free again.
if az cognitiveservices account list-deleted --query "[?name=='$AI'] | [0].name" -o tsv | grep -q .; then
  az cognitiveservices account purge -n "$AI" -g "$RG" -l "$LOC"
  echo "purged: soft-deleted Foundry resource $AI"
fi

if az consumption budget show --budget-name "$BUDGET" -o none 2>/dev/null; then
  az consumption budget delete --budget-name "$BUDGET"
  echo "deleted: budget $BUDGET"
fi
