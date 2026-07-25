#!/usr/bin/env bash
# Fetches backend/.env from GCP Secret Manager using the VM's attached
# service account (via the metadata server — no gcloud CLI or key file
# needed). Run as systemd's ExecStartPre, before uvicorn starts, so the app
# never touches a plaintext secret checked into the repo or set by hand.
# See MVP_Design.md §3.1 (Secrets) / §5.
set -euo pipefail

PROJECT_ID="civic-voice-agent"
SECRET_NAME="civic-voice-backend-env"
ENV_PATH="/home/sumit/civic-voice-agent/backend/.env"

TOKEN=$(curl -s -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

curl -s -H "Authorization: Bearer ${TOKEN}" \
  "https://secretmanager.googleapis.com/v1/projects/${PROJECT_ID}/secrets/${SECRET_NAME}/versions/latest:access" \
  | python3 -c "import sys, json, base64; print(base64.b64decode(json.load(sys.stdin)['payload']['data']).decode(), end='')" \
  > "${ENV_PATH}"

chmod 600 "${ENV_PATH}"
