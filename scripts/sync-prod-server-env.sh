#!/usr/bin/env bash
# Merge GitHub Actions secrets (DB_*, JWT_SECRET) into Swarm server_env and refresh services.
# Run on the self-hosted deploy runner (Swarm manager). Secrets are passed via env, not files in git.
set -euo pipefail

REQUIRED_VARS=(DB_HOST DB_NAME DB_PORT DB_USER DB_PASSWORD JWT_SECRET)
for v in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!v:-}" ]]; then
    echo "ERROR: missing env $v (set from GitHub Actions secrets)"
    exit 1
  fi
done

MERGE_KEYS=(DB_HOST DB_NAME DB_PORT DB_USER DB_PASSWORD JWT_SECRET)
BASE="/tmp/server_env.base.$$"
OUT="/tmp/server_env.merged.$$"
CONFIG_NAME="server_env"

log() {
  echo "[$(date -Iseconds)] $*"
}

if docker config inspect "$CONFIG_NAME" &>/dev/null; then
  log "Reading existing Docker config: $CONFIG_NAME"
  docker config inspect "$CONFIG_NAME" --format pretty | grep '=' >"$BASE" || true
else
  log "WARN: $CONFIG_NAME not found; creating from secrets only"
  : >"$BASE"
fi

python3 - "$BASE" "$OUT" <<'PY'
import os
import sys

base_path, out_path = sys.argv[1], sys.argv[2]
keys = ["DB_HOST", "DB_NAME", "DB_PORT", "DB_USER", "DB_PASSWORD", "JWT_SECRET"]
updates = {k: os.environ[k] for k in keys}

lines: list[str] = []
seen: set[str] = set()
if os.path.exists(base_path) and os.path.getsize(base_path) > 0:
    with open(base_path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if "=" not in line:
                lines.append(line)
                continue
            k, _, _v = line.partition("=")
            if k in updates:
                lines.append(f"{k}={updates[k]}")
                seen.add(k)
            else:
                lines.append(line)

for k in keys:
    if k not in seen:
        lines.append(f"{k}={updates[k]}")

with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
PY

chmod 600 "$OUT"
log "Merged env written (keys updated: ${MERGE_KEYS[*]})"

log "Testing Postgres (pooler) login"
set -a
# shellcheck disable=SC1090
source "$OUT"
set +a
docker run --rm -e PGPASSWORD="$DB_PASSWORD" postgres:16-alpine \
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c 'SELECT 1'

log "Replacing Docker config $CONFIG_NAME"
if docker config inspect "$CONFIG_NAME" &>/dev/null; then
  docker config rm "$CONFIG_NAME" || {
    log "ERROR: could not remove $CONFIG_NAME (still attached?). Remove manually or detach from services."
    exit 1
  }
fi
docker config create "$CONFIG_NAME" "$OUT"

log "Updating bench-api and server task env from merged file"
docker service update --env-file "$OUT" bench-api
docker service update --env-file "$OUT" server

log "Waiting for bench-api..."
sleep 15
docker service ps bench-api --no-trunc 2>/dev/null | head -5 || true
docker service logs bench-api --tail 20 2>&1 || true

log "HTTPS check"
curl -sS -o /dev/null -w "GET /bench/health/ -> %{http_code}\n" https://api.swecc.org/bench/health/ || true
curl -sS https://api.swecc.org/bench/health/ || true
echo ""

rm -f "$BASE" "$OUT"
log "Done"
