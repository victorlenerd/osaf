#!/usr/bin/env bash
# Store the runtime secrets in SSM Parameter Store (read by the ECS task definition).
# Usage:
#   AWS_PROFILE=prod scripts/set_secrets.sh                  # prompts for each value; blank = keep current
#   AWS_PROFILE=prod scripts/set_secrets.sh --from-env .env  # copy non-empty values from an env file
# Values are never echoed. Roll the service afterwards so tasks pick them up.
set -euo pipefail
REGION="${AWS_REGION:-us-east-1}"
NAMES=(MODEL_API_KEY GOOGLE_PLACES_API_KEY WHATSAPP_ACCESS_TOKEN WHATSAPP_PHONE_NUMBER_ID WHATSAPP_VERIFY_TOKEN META_APP_SECRET IG_COOKIES_B64)

put() { # name value
  aws ssm put-parameter --region "$REGION" --name "/afefehub/prod/$1" --type SecureString --value "$2" --overwrite >/dev/null
}

if [ "${1:-}" = "--from-env" ]; then
  FILE="${2:?usage: --from-env FILE}"
  for NAME in "${NAMES[@]}"; do
    VALUE="$(grep -E "^${NAME}=" "$FILE" | tail -n1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
    if [ -z "$VALUE" ] || [ "$VALUE" = "CHANGEME" ]; then
      echo "$NAME: skipped (empty)"
      continue
    fi
    put "$NAME" "$VALUE"
    echo "$NAME: saved (${#VALUE} chars)"
  done
else
  for NAME in "${NAMES[@]}"; do
    read -r -s -p "$NAME: " VALUE
    echo
    [ -z "$VALUE" ] && { echo "  (kept)"; continue; }
    put "$NAME" "$VALUE"
    echo "  saved"
  done
fi
echo "Roll the service to pick them up: scripts/deploy_backend.sh"
