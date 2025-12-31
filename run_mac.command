#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

echo "=================================================="
echo "  AI 阅卷系统（mac 一键测试）"
echo "=================================================="

if ! command -v python3 >/dev/null 2>&1; then
  echo "[错误] 未检测到 python3。请先安装 Python 3。"
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "[1/4] 创建虚拟环境 .venv ..."
  python3 -m venv ".venv"
fi

echo "[2/4] 安装/更新依赖 ..."
".venv/bin/python" -m pip install -U pip
".venv/bin/python" -m pip install -U -r "requirements.txt"

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "[3/4] 请输入 OpenAI API Key（输入时不会回显，回车结束）："
  # shellcheck disable=SC2162
  read -s OPENAI_API_KEY
  echo
  export OPENAI_API_KEY
fi

echo "[4/4] 启动后端：http://localhost:5000"
echo "提示：后端启动后会在浏览器打开 index.html。"

# 尝试打开前端页面
if command -v open >/dev/null 2>&1; then
  open "index.html" || true
fi

exec ".venv/bin/python" "app.py"

