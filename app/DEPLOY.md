# 部署指南（公网可访问 URL）

目标：前端静态托管 + 后端常驻容器，评审点开即用。

## 方案（推荐）：Vercel + 一台容器机

### 1. 后端 → 任意容器平台（Render / Railway / Fly.io / 自己的 VPS）

`backend/Dockerfile` 已备好。以 Render 为例：
1. 仓库推到 GitHub（确认无 .env、无 Key）
2. Render → New Web Service → 选仓库 → Root Directory `app/backend` → Docker
3. 环境变量填入（Render 控制台，不进仓库）：
   - `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`
   - `FUYAO_API_KEY` / `IFIND_AUTH_TOKEN` / `IFIND_MCP_URL`
   - `ALLOW_FIXTURE_FALLBACK=true`（Key 失效时演示兜底）
4. 磁盘：挂 1GB persistent disk 到 `/srv/data`（SQLite 检查点/审计持久化）
5. 得到后端 URL，如 `https://xbuddy-api.onrender.com`

### 2. 前端 → Vercel

1. Vercel → Import 仓库 → Root Directory `app/frontend`
2. 构建前把 `next.config.mjs` 的 rewrite 目标改为后端公网 URL（用环境变量 `API_ORIGIN` 注入，已预留：无该变量时回退 localhost:8000）
3. 得到 `https://xxx.vercel.app` —— 即交付的 Web 产品 URL

### 3. 交付前检查单

- [ ] 公网 URL 打开 → 新建研究目标 → 全流程走通
- [ ] 刷新页面断点恢复可用（检查 SQLite 持久磁盘已挂）
- [ ] 工具卡 auth 字段：真实 Key 时不再显示 fixture 提示
- [ ] 评审可能乱输：合规拦截、不存在标的、停止规则各试一次
- [ ] 仓库主页 README 的"启动方式"与线上一致；仓库内全文搜索无 key/token 泄露

## 备选：全本地 + 隧道（临时演示用，不建议作为交付 URL）

```bash
cd app/backend && uv run uvicorn app.main:app --port 8000 &
cd app/frontend && npm run build && npm run start &
# 隧道二选一
cloudflared tunnel --url http://localhost:3000
# 或 ngrok http 3000
```
注意：前端 rewrite 指向 localhost:8000 指的是**服务器侧**的 localhost，同机部署时成立；隧道只需暴露 3000。

## 已上线（2026-09-24，腾讯云香港 CVM 43.161.244.43）

**生产 URL：https://alphabuddy.site**（www 301 跳转；Caddy 自动签 Let's Encrypt，证书已签发）

### 最终架构

```
公网 ──TLS──> Caddy(80/443, systemd)
                ├── alphabuddy.site        → reverse_proxy 127.0.0.1:3000
                └── www.alphabuddy.site    → 301 → alphabuddy.site
Next.js (127.0.0.1:3000, systemd alphabuddy-frontend)
                └── /api/*  server 侧 rewrite → http://localhost:8000
FastAPI+LangGraph (127.0.0.1:8000, systemd alphabuddy-backend)
                └── 真实数据源：扶摇 X-api-key / iFinD MCP Bearer / DeepSeek LLM（.env chmod 600）
```

代码位于服务器 `~/alphabuddy`（rsync 同步，排除 .git/node_modules/.next/.venv/data/.env）；
密钥仅经 scp 单通道传输，不进仓库、不落日志。

### 上线验收记录（2026-09-24 全部通过）

- `curl -I https://alphabuddy.site` → HTTP/2 200，首页含 AlphaBuddy
- `https://alphabuddy.site/api/capabilities` → 200（5 工具）
- E2E：建线程（thesis_check 寒武纪）→ run（SSE 逐条到达，经 Caddy 无缓冲）→ approve → run
  → status=done，4 个工具卡 auth=ok（真实数据），报告含判定句+证据清单
- 韧性：`systemctl restart alphabuddy-backend alphabuddy-frontend` 后公网 200 自愈
- 安全组：80/443 已在腾讯云控制台放行（LE HTTP-01 验证从公网打通即为证据）

### systemd 命令速查

```bash
sudo systemctl status|restart|stop alphabuddy-backend alphabuddy-frontend
sudo journalctl -u alphabuddy-backend -f          # 后端日志（SSE/工具调用）
sudo journalctl -u alphabuddy-frontend -f         # 前端日志
sudo systemctl reload caddy                        # Caddyfile 变更后
sudo caddy validate --config /etc/caddy/Caddyfile  # 改配置前先验证
```

### 更新发布流程

```bash
# 本地
rsync -az --delete --exclude='.git' --exclude='deer-flow' --exclude='**/node_modules' \
  --exclude='**/.next' --exclude='**/.venv' --exclude='**/data' --exclude='**/.env' \
  --exclude='.DS_Store' --exclude='**/__pycache__' \
  -e "ssh -i ~/.ssh/tencent_lhkp.pem" /Users/yuyue/xbuddy/ ubuntu@43.161.244.43:~/alphabuddy/
# 服务器
ssh -i ~/.ssh/tencent_lhkp.pem ubuntu@43.161.244.43 '
  export PATH="$HOME/.local/bin:$PATH"
  cd ~/alphabuddy/app/backend && uv sync
  cd ~/alphabuddy/app/frontend && npm install --no-audit --no-fund && NODE_OPTIONS=--max-old-space-size=1024 npm run build
  sudo systemctl restart alphabuddy-backend alphabuddy-frontend'
```
注意：前端代码变更必须重新 build；仅后端变更可跳过 npm 步骤。
