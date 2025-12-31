#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

BIN="$ROOT_DIR/dist/AIGrader"
if [ ! -x "$BIN" ]; then
  echo "[错误] 未找到可执行文件：$BIN"
  echo "请先运行 ./build_mac_pyinstaller.command 生成 dist/AIGrader"
  exit 1
fi

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "请输入 OpenAI API Key（输入时不会回显，回车结束）："
  # shellcheck disable=SC2162
  read -s OPENAI_API_KEY
  echo
  export OPENAI_API_KEY
fi

if command -v open >/dev/null 2>&1; then
  open "http://localhost:5000/" || true
fi

exec "$BIN"

