#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
runtime_bin="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin"
if [ -x "$runtime_bin/node" ]; then
  export PATH="$runtime_bin:$PATH"
fi
if ! command -v node >/dev/null 2>&1 || ! node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>22||(a===22&&b>=13)?0:1)' 2>/dev/null; then
  echo 'Node.js 22.13 or newer is required. Node.js 24 is recommended.'
  exit 1
fi
if [ ! -d node_modules ]; then
  echo 'First run: installing dependencies. Keep the network connection available.'
  npm_config_cache="$PWD/.cache/npm" npm ci
fi
echo 'Starting HomeNest at http://localhost:5173/'
echo 'The deterministic demo works without an API key. Press Control+C to stop.'
exec npm run dev -- --host 127.0.0.1 --port 5173
