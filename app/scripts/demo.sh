#!/usr/bin/env bash
# 研 Buddy 一键演示启动：后端(8000) + 前端生产(3000) + 临时公网隧道
# 用法：app/scripts/demo.sh [stop]
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG=/tmp/xbuddy
mkdir -p "$LOG"

stop_all() {
  pkill -f "uvicorn app.main" 2>/dev/null
  pkill -f "next start" 2>/dev/null
  pkill -f "cloudflared tunnel" 2>/dev/null
  echo "已停止后端 / 前端 / 隧道"
}

if [ "${1:-}" = "stop" ]; then stop_all; exit 0; fi

stop_all >/dev/null 2>&1
sleep 1

cd "$ROOT/backend"
[ -f .env ] || cp ../.env.example .env
(uv run uvicorn app.main:app --port 8000 > "$LOG/backend.log" 2>&1 &)
echo "后端启动中…"

cd "$ROOT/frontend"
if [ ! -d .next ]; then
  echo "首次运行，构建前端…"
  npm run build > "$LOG/build.log" 2>&1 || { echo "构建失败，见 $LOG/build.log"; exit 1; }
fi
(npm run start > "$LOG/frontend.log" 2>&1 &)
echo "前端启动中…"

(cloudflared tunnel --url http://localhost:3000 > "$LOG/tunnel.log" 2>&1 &)

for i in $(seq 1 20); do
  sleep 2
  URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$LOG/tunnel.log" | head -1)
  [ -n "$URL" ] && curl -sf -o /dev/null --max-time 5 "$URL/" && break
done

echo
echo "======================================"
echo " 本地：  http://localhost:3000"
echo " 公网：  ${URL:-隧道未就绪，见 $LOG/tunnel.log}"
echo " 停止：  $0 stop"
echo "======================================"
[ -n "${URL:-}" ] && open "$URL" 2>/dev/null
