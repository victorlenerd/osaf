#!/usr/bin/env bash
# Store the runtime secrets in SSM Parameter Store (read by the ECS task definition).
# Usage: AWS_PROFILE=prod scripts/set_secrets.sh   (prompts for each value; blank = keep current)
set -euo pipefail
REGION="${AWS_REGION:-us-east-1}"
for NAME in MODEL_API_KEY GOOGLE_PLACES_API_KEY WHATSAPP_ACCESS_TOKEN WHATSAPP_PHONE_NUMBER_ID WHATSAPP_VERIFY_TOKEN META_APP_SECRET IG_COOKIES_B64; do
  read -r -s -p "$NAME: " VALUE; echo
  [ -z "$VALUE" ] && { echo "  (kept)"; continue; }
  aws ssm put-parameter --region "$REGION" --name "/afefehub/prod/$NAME" --type SecureString --value "$VALUE" --overwrite >/dev/null
  echo "  saved"
done
echo "Roll the service to pick them up: scripts/deploy_backend.sh"
