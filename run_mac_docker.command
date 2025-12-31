#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "[错误] 未检测到 docker。请先安装 Docker Desktop for Mac。"
  exit 1
fi

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "请输入 OpenAI API Key（输入时不会回显，回车结束）："
  # shellcheck disable=SC2162
  read -s OPENAI_API_KEY
  echo
  export OPENAI_API_KEY
fi

IMAGE="ai-grader:local"

echo "构建镜像：$IMAGE"
docker build -t "$IMAGE" .

echo "启动容器：http://localhost:5000/"
if command -v open >/dev/null 2>&1; then
  open "http://localhost:5000/" || true
fi

exec docker run --rm -p 5000:5000 -e OPENAI_API_KEY="$OPENAI_API_KEY" "$IMAGE"

