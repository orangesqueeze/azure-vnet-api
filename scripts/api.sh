#!/usr/bin/env bash
# Call the deployed VNet API with your own Entra token (API URL and client ID come from Terraform outputs).
set -euo pipefail

cd "$(dirname "$0")/.."
API_URL="${API_URL:-$(terraform -chdir=infra output -raw api_url)}"
API_CLIENT_ID="${API_CLIENT_ID:-$(terraform -chdir=infra output -raw api_client_id)}"

usage() {
  cat <<'EOF'
Usage:
  scripts/api.sh health
  scripts/api.sh list
  scripts/api.sh get <name>
  scripts/api.sh create <name> <address-space> <subnet>=<cidr> [<subnet>=<cidr> ...]
  scripts/api.sh noauth            # expect 401

Example:
  scripts/api.sh create demo-vnet 10.0.0.0/16 web=10.0.1.0/24 db=10.0.2.0/24

Set AZURE_CONFIG_DIR first if you use a separate az profile (e.g. ~/.azure-personal).
EOF
}

call() {
  local method=$1 path=$2 body=${3:-} token response
  token=$(az account get-access-token --scope "api://$API_CLIENT_ID/.default" --query accessToken -o tsv)
  if [[ -n "$body" ]]; then
    response=$(curl -sS -m 120 -X "$method" "$API_URL$path" -H "Authorization: Bearer $token" \
      -H "Content-Type: application/json" -d "$body" -w $'\n%{http_code}')
  else
    response=$(curl -sS -m 120 -X "$method" "$API_URL$path" -H "Authorization: Bearer $token" -w $'\n%{http_code}')
  fi
  echo "HTTP ${response##*$'\n'}"
  echo "${response%$'\n'*}" | python3 -m json.tool
}

case "${1:-}" in
  health)
    curl -sS -m 60 -w $'\nHTTP %{http_code}\n' "$API_URL/health"
    ;;
  list)
    call GET /vnets
    ;;
  get)
    call GET "/vnets/${2:?name required}"
    ;;
  create)
    name=${2:?name required}
    address_space=${3:?address space required}
    shift 3
    body=$(python3 - "$name" "$address_space" "$@" <<'PY'
import json
import sys

name, address_space, *subnets = sys.argv[1:]
print(json.dumps({
    "name": name,
    "addressSpace": [address_space],
    "subnets": [{"name": n, "addressPrefix": p} for n, p in (s.split("=", 1) for s in subnets)],
}))
PY
)
    call POST /vnets "$body"
    ;;
  noauth)
    curl -sS -m 60 -w $'\nHTTP %{http_code}\n' "$API_URL/vnets"
    ;;
  *)
    usage
    ;;
esac
