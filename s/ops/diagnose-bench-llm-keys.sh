#!/bin/bash
# Compare Swarm Docker configs vs running bench-api/bench-worker env for LLM keys,
# then probe Anthropic via LiteLLM using the same env extraction deploy.sh uses.
#
# Safe for CI: never prints secret values (length + prefix only).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
. "${REPO_ROOT}/s/lib.sh"

IMAGE="${DIAGNOSE_BENCH_API_IMAGE:-}"
PROBE="${REPO_ROOT}/services/bench/scripts/docker_test_anthropic.py"
WORKDIR="${RUNNER_TEMP:-/tmp}/bench-llm-diagnose"
FAIL=0

usage() {
  cat <<EOF
Usage: $0

Environment:
  DOCKERHUB_USERNAME   Docker Hub org/user (default: swecc)
  DIAGNOSE_BENCH_API_IMAGE  Override bench-api image (default: \$DOCKERHUB_ORG/swecc-bench-api:latest)

Runs on the swarm manager (self-hosted deploy runner). Writes a summary to
GITHUB_STEP_SUMMARY when set.
EOF
  exit 1
}

[[ "${1:-}" != "-h" && "${1:-}" != "--help" ]] || usage

require_cmd docker
require_cmd python3
[[ -f "$PROBE" ]] || die "Probe script not found: $PROBE"

mkdir -p "$WORKDIR"

if [[ -z "$IMAGE" ]]; then
  IMAGE="$(docker_image bench-api latest)"
fi

summary() {
  echo "$1"
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    echo "$1" >>"$GITHUB_STEP_SUMMARY"
  fi
}

# Print whether KEY is set in a KEY=value file (no values logged).
env_file_key_status() {
  local label="$1"
  local file="$2"
  local key="$3"
  local line val len prefix

  if [[ ! -f "$file" ]]; then
    echo "${label}: file missing"
    return 1
  fi

  line="$(grep -E "^${key}=" "$file" | tail -1 || true)"
  if [[ -z "$line" ]]; then
    echo "${label}: ${key} absent"
    return 1
  fi

  val="${line#${key}=}"
  len="${#val}"
  if [[ "$len" -eq 0 ]]; then
    echo "${label}: ${key} present but EMPTY"
    return 1
  fi

  prefix="${val:0:12}"
  echo "${label}: ${key} set (len=${len}, prefix=${prefix}...)"
  return 0
}

# Swarm service spec env (what running tasks should receive).
service_key_status() {
  local svc="$1"
  local key="$2"

  if ! docker service inspect "$svc" &>/dev/null; then
    echo "service ${svc}: not found"
    return 1
  fi

  local raw val len prefix
  raw="$(docker service inspect "$svc" --format '{{range .Spec.TaskTemplate.ContainerSpec.Env}}{{println .}}{{end}}' \
    | grep -E "^${key}=" | tail -1 || true)"

  if [[ -z "$raw" ]]; then
    echo "service ${svc}: ${key} absent from Spec.TaskTemplate.ContainerSpec.Env"
    return 1
  fi

  val="${raw#${key}=}"
  len="${#val}"
  if [[ "$len" -eq 0 ]]; then
    echo "service ${svc}: ${key} present but EMPTY"
    return 1
  fi

  prefix="${val:0:12}"
  echo "service ${svc}: ${key} set (len=${len}, prefix=${prefix}...)"
  return 0
}

# Running task container env (what the live process actually sees).
running_task_key_status() {
  local svc="$1"
  local key="$2"

  local cid
  cid="$(docker ps --filter "label=com.docker.swarm.service.name=${svc}" -q | head -1 || true)"
  if [[ -z "$cid" ]]; then
    echo "running ${svc}: no running container"
    return 1
  fi

  docker exec "$cid" python3 -c "
import os
k = (os.environ.get('${key}') or '').strip()
print(f'running ${svc}: ${key} set={bool(k)} len={len(k)} prefix={(k[:12] + \"...\") if k else \"-\"}')"
}

extract_config_json() {
  local config_name="$1"
  local out="$2"
  docker config inspect "$config_name" --format '{{json .Spec.Data}}' \
    | python3 -c "import sys, json, base64; sys.stdout.buffer.write(base64.b64decode(json.load(sys.stdin)))" \
    >"$out"
}

extract_config_deploy_style() {
  local config_name="$1"
  local out="$2"
  docker config inspect "$config_name" --format pretty | grep -e '=' >"$out" || true
}

compare_extractions() {
  local config_name="$1"
  local json_file="$WORKDIR/${config_name}.json.txt"
  local pretty_file="$WORKDIR/${config_name}.pretty.txt"

  if ! docker config ls --filter "name=${config_name}" -q | grep -q .; then
    summary "- **${config_name}**: Docker config not found on swarm"
    FAIL=1
    return
  fi

  extract_config_json "$config_name" "$json_file"
  extract_config_deploy_style "$config_name" "$pretty_file"

  summary "### Docker config \`${config_name}\`"
  env_file_key_status "config (json decode)" "$json_file" "ANTHROPIC_API_KEY" || FAIL=1
  env_file_key_status "config (json decode)" "$json_file" "OPENAI_API_KEY" || true
  env_file_key_status "config (deploy pretty|grep)" "$pretty_file" "ANTHROPIC_API_KEY" || FAIL=1

  local json_len pretty_len
  json_len="$(grep -E '^ANTHROPIC_API_KEY=' "$json_file" | tail -1 | cut -d= -f2- | wc -c | tr -d ' ')"
  pretty_len="$(grep -E '^ANTHROPIC_API_KEY=' "$pretty_file" | tail -1 | cut -d= -f2- | wc -c | tr -d ' ')"
  # wc -c includes newline; compare roughly
  if [[ "$json_len" -gt 1 && "$pretty_len" -le 1 ]]; then
    summary "- **MISMATCH**: json decode has ANTHROPIC_API_KEY but deploy \`pretty|grep\` extraction does not"
    FAIL=1
  fi

  cp "$pretty_file" "$WORKDIR/${config_name}.deploy_env.tmp"
}

run_litellm_probe() {
  local label="$1"
  local env_file="$2"

  summary "### LiteLLM probe — ${label}"

  if ! grep -qE '^ANTHROPIC_API_KEY=.+$' "$env_file"; then
    summary "- Skipped: no ANTHROPIC_API_KEY in env file"
    FAIL=1
    return
  fi

  log INFO "Pulling ${IMAGE}"
  docker pull "$IMAGE" >/dev/null

  set +e
  docker run --rm \
    --env-file "$env_file" \
    -v "${PROBE}:/probe.py:ro" \
    "$IMAGE" \
    python /probe.py
  local rc=$?
  set -e

  if [[ $rc -ne 0 ]]; then
    summary "- Probe exited ${rc}"
    FAIL=1
  fi
}

probe_running_container() {
  local svc="$1"
  local cid
  cid="$(docker ps --filter "label=com.docker.swarm.service.name=${svc}" -q | head -1 || true)"
  if [[ -z "$cid" ]]; then
    summary "### Running container probe — ${svc}: no container"
    return
  fi

  summary "### Running container probe — ${svc} (\`${cid:0:12}\`)"
  running_task_key_status "$svc" "ANTHROPIC_API_KEY" || FAIL=1
  running_task_key_status "$svc" "OPENAI_API_KEY" || true

  set +e
  docker cp "$PROBE" "${cid}:/tmp/probe.py"
  docker exec "$cid" python /tmp/probe.py
  local rc=$?
  docker exec "$cid" rm -f /tmp/probe.py 2>/dev/null || true
  set -e

  if [[ $rc -ne 0 ]]; then
    summary "- In-container probe exited ${rc}"
    FAIL=1
  fi
}

main() {
  summary "## Bench LLM key diagnosis"
  summary ""
  summary "Image: \`${IMAGE}\`"
  summary ""

  for config in bench-api_env bench-worker_env; do
    compare_extractions "$config"
    summary ""
  done

  summary "### Swarm service spec env"
  service_key_status "bench-api" "ANTHROPIC_API_KEY" || FAIL=1
  service_key_status "bench-api" "OPENAI_API_KEY" || true
  service_key_status "bench-worker" "ANTHROPIC_API_KEY" || FAIL=1
  summary ""

  run_litellm_probe "bench-api_env via deploy-style extraction" "$WORKDIR/bench-api_env.deploy_env.tmp"
  summary ""

  probe_running_container "bench-api"
  summary ""

  if [[ $FAIL -ne 0 ]]; then
    summary ""
    summary "**Result: FAIL** — see lines above for config vs service vs LiteLLM mismatches."
    exit 1
  fi

  summary ""
  summary "**Result: PASS** — config, service, and LiteLLM probes aligned."
}

main
