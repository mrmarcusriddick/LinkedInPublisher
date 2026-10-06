#!/usr/bin/env bash
# Update the existing deployment; never create resources or enable publishing.
set -euo pipefail
cd "$(dirname "$0")/.."
az account set --subscription a2e23015-1a59-4109-9126-cd464798993f
source .venv/bin/activate
python -m app.import_queue --validate-only
# Fail before deployment if LinkedIn cannot process the personal image.
python -m app.check_image
publisher_tag="publisher:$(git rev-parse --short=16 HEAD)"
az acr build --registry c2ea2e23015 --image "$publisher_tag" .
az containerapp job update \
  --resource-group rg-cloud2e-publisher --name c2ea2e23015 \
  --image "c2ea2e23015.azurecr.io/$publisher_tag" \
  --cron-expression '*/5 12,13,14 * * *' \
  --set-env-vars REQUIRE_IMAGES=true --output none
az containerapp job show \
  --resource-group rg-cloud2e-publisher --name c2ea2e23015 \
  --query "properties.template.containers[0].{image:image,settings:env[?name=='PUBLISH_ENABLED' || name=='REQUIRE_IMAGES']}" \
  --output json
