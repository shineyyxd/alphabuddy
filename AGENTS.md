# AGENTS.md — 给 AI Coding 工具的项目上下文

## 项目是什么
题目 13「投资 X Buddy」参赛作品：面向投资研究者的透明 Agent 工作台。
架构蓝图见仓库根目录上一级的 `ARCHITECTURE.md`（若不在仓库内则以本文件为准）；
前后端契约见 `app/docs/API_CONTRACT.md`（**修改 API 前先改契约并同步两侧**）。

## 目录
- `app/backend/`：FastAPI + LangGraph（Python 3.12，uv）。图：supervisor→planner(interrupt 审批)→researcher→reporter。工具层统一信封 `{data,source,as_of,unit,caliber}`。
- `app/frontend/`：Next.js 14 App Router + Tailwind。三栏（线程/步骤流/产物）+ 成本条。`?mock=1` 回放模式。
- `app/backend/fixtures/`：寒武纪 688256.SH 2026 中报已验证数据，无 Key 时回放。

## 铁律
1. 合规：不输出涨跌预测/买卖建议；输入守卫在 `backend/app/guard.py`。
2. 产物中的关键数字必须由后端从工具信封渲染，LLM 只写解释文字。
3. 工具失败 → 错误信封 + 显式降级卡，禁止静默跳过或编造。
4. 密钥只走环境变量（`.env`，已 gitignore），任何 key 不得进仓库。
5. Harness 能力用 LangGraph 内置（checkpointer/interrupt/Store），禁止自写替代。

## 常用命令
```bash
cd app/backend && uv run pytest                 # 后端测试（22 个）
cd app/backend && uv run uvicorn app.main:app --port 8000
cd app/frontend && npm run build && npm run start   # 不要在 dev 运行时 build
```

## 测试交付物
`app/TESTING.md`（T1–T12 执行记录）、`app/AI_LOG.md`（AI 使用与修正记录）、`app/VIDEO_SCRIPT.md`、`app/DEPLOY.md`。
