"""Test-wide settings. Tests must never call Azure.

`backend/.env` may hold a real Foundry endpoint (written by scripts/azure/provision.sh).
pydantic-settings lets environment variables override .env, so blanking the endpoint here,
before `formline.config` is imported, keeps every test on the fake model.
"""

import os

os.environ["AZURE_AI_PROJECT_ENDPOINT"] = ""
