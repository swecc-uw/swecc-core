#!/usr/bin/env bash
# Push bench model-provider secrets to swecc-uw/swecc-infra (Swarm sync-configs source).
# Usage:
#   export OPENAI_API_KEY=sk-...
#   export ANTHROPIC_API_KEY=sk-ant-...
#   ./infra/push-bench-secrets.sh
#
# Or pass a file (KEY=value lines, no export needed):
#   ./infra/push-bench-secrets.sh /path/to/bench-secrets.env
set -euo pipefail

REPO="${SWECC_INFRA_REPO:-swecc-uw/swecc-infra}"
KEYS=(
  OPENAI_API_KEY
  ANTHROPIC_API_KEY
  DEEPSEEK_API_KEY
  XAI_API_KEY
)

if ! command -v gh >/dev/null 2>&1; then
  echo "error: gh CLI required" >&2
  exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "error: run gh auth login first" >&2
  exit 1
fi

load_env_file() {
  local file="$1"
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "$line" == \#* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    export "$key=$value"
  done <"$file"
}

if [[ "${1:-}" != "" && -f "${1:-}" ]]; then
  load_env_file "$1"
fi

set_count=0
skip_count=0
for key in "${KEYS[@]}"; do
  value="${!key:-}"
  if [[ -z "$value" ]]; then
    echo "skip $key (not set)"
    skip_count=$((skip_count + 1))
    continue
  fi
  echo "set $key → $REPO"
  gh secret set "$key" --body "$value" --repo "$REPO"
  set_count=$((set_count + 1))
done

echo ""
echo "Done: $set_count set, $skip_count skipped."
if [[ "$set_count" -gt 0 ]]; then
  echo "Trigger sync: gh workflow run sync-configs.yml --repo $REPO"
fi
if [[ "$skip_count" -gt 0 ]]; then
  echo "Missing keys must be provided before bench evals can call those providers."
fi
