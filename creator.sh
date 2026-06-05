#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
PYTHON_BIN="${PYTHON_BIN:-}"
OPEN_BROWSER="false"

if [[ "${1:-}" == "--open" ]]; then
    OPEN_BROWSER="true"
fi

if [[ -z "$PYTHON_BIN" ]]; then
    if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
        PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v python3)"
    else
        echo "Python not found. Expected .venv/bin/python or python3 on PATH." >&2
        exit 1
    fi
fi

if [[ -f "$ROOT_DIR/setup_cuda_env.sh" ]]; then
    # shellcheck disable=SC1091
    set +u
    source "$ROOT_DIR/setup_cuda_env.sh"
    set -u
fi

URL="http://${HOST}:${PORT}/"

echo "Starting JC Video Factory"
echo "Web + bot: $URL"
echo "Press Ctrl+C to stop."

if [[ "$OPEN_BROWSER" == "true" ]]; then
    if command -v open >/dev/null 2>&1; then
        (sleep 3 && open "$URL") >/dev/null 2>&1 &
    else
        echo "Open this URL in your browser: $URL"
    fi
fi

exec "$PYTHON_BIN" -m uvicorn app.asgi:app --host "$HOST" --port "$PORT"
