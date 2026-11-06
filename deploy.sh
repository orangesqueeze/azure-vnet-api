#!/usr/bin/env bash
# One-command setup: infra (Terraform) + code deploy.
set -euo pipefail

SUB="${SUB:-$(az account show --query id -o tsv)}"

terraform -chdir=infra init -input=false
terraform -chdir=infra apply -auto-approve -input=false -var "subscription_id=$SUB" \
  ${RG:+-var "resource_group_name=$RG"} ${LOCATION:+-var "location=$LOCATION"}

APP=$(terraform -chdir=infra output -raw function_app_name)
func azure functionapp publish "$APP" --python

echo "API_URL=$(terraform -chdir=infra output -raw api_url)"
echo "API_CLIENT_ID=$(terraform -chdir=infra output -raw api_client_id)"
