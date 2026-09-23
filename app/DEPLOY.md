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
