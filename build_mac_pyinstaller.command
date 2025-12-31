#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

echo "=================================================="
echo "  mac 打包（PyInstaller -> dist/AIGrader）"
echo "=================================================="

if ! command -v python3 >/dev/null 2>&1; then
  echo "[错误] 未检测到 python3。请先安装 Python 3（建议官方安装包或 brew）。"
  exit 1
fi

if [ ! -d ".venv_build" ]; then
  echo "[1/4] 创建打包虚拟环境 .venv_build ..."
  python3 -m venv ".venv_build"
fi

echo "[2/4] 安装依赖 + pyinstaller ..."
".venv_build/bin/python" -m pip install -U pip
".venv_build/bin/python" -m pip install -U -r "requirements.txt" pyinstaller

echo "[3/4] 清理旧产物 ..."
rm -rf "build" "dist" "__pycache__" "*.spec" || true

echo "[4/4] 开始打包（会生成 dist/AIGrader）..."
# mac 的 --add-data 分隔符使用 :
".venv_build/bin/python" -m PyInstaller \
  --noconfirm \
  --onefile \
  --name "AIGrader" \
  --add-data "index.html:." \
  "app.py"

echo "✅ 打包完成：$ROOT_DIR/dist/AIGrader"
echo "运行方式："
echo "  OPENAI_API_KEY='你的key' \"$ROOT_DIR/dist/AIGrader\""

