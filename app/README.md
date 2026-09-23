# 研 Buddy — 面向投资研究者的透明 Agent 工作台

> 题目 13「投资 X Buddy」参赛作品。给一个研究目标，它出计划、调真实金融数据、全程可见可控，产出带证据与待核实事项的研究产物。

## 产品选择

机构级方案（腾讯 WorkBuddy 金融版、Kimi 金融行业方案）把"数据 MCP 化 + 技能封装 + 多 Agent + 审批 + 可审计"卖给券商等机构；财搭子把多智能体包装成面向小白股民的托管产品。本产品验证：**同一套架构在个人研究者场景可以轻量落地，且把 Agent Harness 的内部状态（计划、工具调用、检查点、成本）全部透明化**——这是消费级产品（财搭子）藏起来、机构级产品（WorkBuddy）不面向个人的一层。

- **用户**：个人投资研究者（写研报/做决策前需要可验证的研究助手）
- **非目标**：不做涨跌预测/收益承诺/买卖建议（合规红线）；不做实时推送；不做多用户组织治理；不做账户体系

## 架构

见 [/Users/yuyue/xbuddy/ARCHITECTURE.md](../ARCHITECTURE.md)。要点：

- **Agent 层**（LangGraph）：Supervisor → Planner → **interrupt 人工审批** → Researcher（工具循环）→ Reporter
- **技能层**：3 张预置任务卡（命题验证 / 业绩点评 / 持仓早报）= prompt 模板 + 工具白名单 + 固定产物格式
- **工具层**：扶摇（行情/估值/财务指标/报表）+ iFinD MCP（指标/报表/公告），统一返回 `{data, source, as_of, unit, caliber}`，每次调用写审计日志
- **Harness 层**：SQLite Checkpointer（断点恢复）、Store（长期记忆）、recursion_limit + token 预算 + 单工具 10s 超时（停止规则）、上下文压缩
- **合规层**（参考 Kimi 金融方案风险评估网关）：输入拦截、授权检查落实到每次调用、产物数字可回指工具返回、强制"待核实事项"章节、审计全程可查
- **可观测**：Langfuse（可选）/ 内置计数 → 前端成本条

## 启动方式

```bash
cp .env.example .env   # 填入 LLM_API_KEY / FUYAO_API_KEY / IFIND_AUTH_TOKEN
# 后端
cd backend && uv sync && uv run uvicorn app.main:app --port 8000
# 前端（生产模式）
cd frontend && npm install && npm run build && npm run start   # http://localhost:3000
```

无任何 Key 时 `ALLOW_FIXTURE_FALLBACK=true` 进入 fixture 回放模式（寒武纪案例可完整演示），数据源不可用的步骤会显式标红降级。公网部署见 [DEPLOY.md](./DEPLOY.md)（含隧道应急方案）。

## AI 的角色

- 开发与架构：Kimi Code（K2/K3）全程 AI Coding；候选人负责架构决断、契约设计、数据验证与错误修正（见 [AI_LOG.md](./AI_LOG.md)）
- 产品内 LLM：Kimi API（OpenAI 兼容），承担意图识别、计划生成、报告措辞；**所有关键数字由程序从工具返回渲染，LLM 不可编造**

## 数据来源

- 扶摇（同花顺金融数据，https://fuyao.aicubes.cn）：行情快照、估值、财务指标、三大报表
- iFinD MCP（https://mcp.51ifind.com）：财务指标、报表、公告
- 所有证据卡固定四要素：来源、时点、单位、统计口径

## 已知边界与未做事项

- 记忆为单用户本地 Store，无多用户隔离
- 持仓早报的定时触发为演示级（进程内调度），非生产级任务队列
- 冲突检测为"同字段双源/双期不一致"规则，未做语义级矛盾识别
- 未做：实时推送、移动端、券商实盘对接（合规红线，主动不做）

## 测试与演示

- 测试说明见 [TESTING.md](./TESTING.md)
- 演示视频：（待录）
