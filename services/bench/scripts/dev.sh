#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
UI_PORT="${UI_PORT:-3000}"

cleanup() {
  echo ""
  echo "Shutting down…"
  kill "$BACKEND_PID" "$UI_PID" 2>/dev/null || true
  wait "$BACKEND_PID" "$UI_PID" 2>/dev/null || true
  echo "Done."
}
trap cleanup EXIT INT TERM

cd "$ROOT"

# ── Backend ────────────────────────────────────────────────────────────────────
echo "Starting backend on http://localhost:$BACKEND_PORT …"
.venv/bin/uvicorn src.api.app:app \
  --host 0.0.0.0 \
  --port "$BACKEND_PORT" \
  --reload \
  --log-level info &
BACKEND_PID=$!

# Wait for the backend to be ready (up to 15 s)
echo -n "Waiting for backend"
for i in $(seq 1 30); do
  if curl -sf "http://localhost:$BACKEND_PORT/health" > /dev/null 2>&1; then
    echo " ready."
    break
  fi
  echo -n "."
  sleep 0.5
  if [ "$i" -eq 30 ]; then
    echo ""
    echo "ERROR: Backend did not start within 15 s. Check for errors above."
    exit 1
  fi
done

# ── Seed example domain (idempotent) ──────────────────────────────────────────
echo "Seeding example domain…"
.venv/bin/python scripts/seed_example_domain.py --api-url "http://localhost:$BACKEND_PORT" || true

# ── UI ────────────────────────────────────────────────────────────────────────
echo "Starting UI on http://localhost:$UI_PORT …"
cd "$ROOT/ui"
NEXT_PUBLIC_API_URL="http://localhost:$BACKEND_PORT" \
  npm run dev -- --port "$UI_PORT" &
UI_PID=$!

echo ""
echo "══════════════════════════════════════════════════════"
echo "  Backend  → http://localhost:$BACKEND_PORT"
echo "  API Docs → http://localhost:$BACKEND_PORT/docs"
echo "  UI       → http://localhost:$UI_PORT"
echo "  Press Ctrl+C to stop both."
echo "══════════════════════════════════════════════════════"
echo ""

wait
