# AI 使用与验证记录（题目 13 交付物）

## 使用了哪些 AI、参与哪些环节

| 环节 | AI 工具 | 参与方式 |
|---|---|---|
| 选题与架构设计 | Kimi Code（K3） | 题目分析、竞品调研（财搭子/WorkBuddy 金融版/Kimi 金融方案）、架构蓝图起草；候选人做最终决断（fork deer-flow → 改为自建轻量 LangGraph） |
| 竞品与数据源调研 | Kimi Code 联网检索 | 公开资料架构推演；候选人甄别事实与推断 |
| 后端开发 | Kimi Code coder 子代理 | 按契约实现；候选人审查关键模块（合规守卫、信封结构） |
| 前端开发 | Kimi Code coder 子代理 | 三栏 UI 实现；候选人验收交互 |
| 产品内 LLM | DeepSeek deepseek-flash（OpenAI 兼容） | 报告结论解读（判定与数字由程序渲染）；此前为 Kimi API 设计，接口兼容可切换 |
| 数据验证 | iFinD 插件实测 | 寒武纪证据链字段级验证（题目③阶段完成） |

## 候选人修正 AI 错误的记录（随手记，真实优先）

| # | AI 做了什么 | 错在哪 | 怎么发现/修正 |
|---|---|---|---|
| 1 | 架构选型建议 fork deer-flow | 评估后其前端与研究流耦合过深，改造成本高于自建 | 候选人决断改为自建轻量 LangGraph 后端，deer-flow 仅作参照 |
| 2 | 生成工具信封的 as_of 取值 | iFinD 证据卡时点显示为报告期代号"2026-2"而非日期 | 联调时对照证据卡四要素发现；修正 _guess_as_of 解包 JSON-RPC/MCP 包裹并优先取 period_end（2026-06-30） |
| 3 | 实现计划审批的编辑分支 | 编辑后计划丢失工具参数（客户端只回传 id/title/tool），全任务崩溃 `missing required argument: 'thscode'` | T2 用例实测复现；修复：planner 编辑分支补默认参数 + registry 捕获 TypeError 转 bad_params 信封 |
| 4 | 生成公告工具信封 | ifind_announcement 信封缺 as_of，公告日期埋在 data 内部字段，四要素不齐 | 评测集 v1 基线跑出四要素齐全率 0.75 暴露；修复 _guess_as_of 解包公告首条日期，v2 复跑全绿（20/20） |
| 5 | 按假想 MCP 工具名实现 iFinD 客户端 | 真实 iFinD MCP（2026-09-24 tools/list）全部是自然语言 query 风格工具，无 fin_indicator/announcement 这类结构化工具 | 真机联调暴露；改为 get_stock_financials/get_stock_events + 中文 query 构造 + markdown 表格健壮解析（解析失败原文入 data）；ifind_news 无对应工具从注册表移除 |
| 6 | 信任 iFinD 返回与请求标的一致 | 请求 999999.SH（不存在）被 iFinD 模糊匹配成 601999.SH 出版传媒并返回其真实财务数据——静默错数据，且污染长期记忆被后续会话引用 | 评测集 deg-02 防编造核验 FAIL 顺藤摸瓜发现；修复：normalize 校验返回表格证券代码与请求一致，不一致按标的不存在转 api_error 错误信封；normalize 异常纳入 _call 降级捕获 |
| 7 | LLM 结论 prompt 只禁止"不存在的数字" | deepseek-flash 把投资收益 0.83 亿+其他收益 1.67 亿加成"约 2.51 亿"（算术衍生物，信封里没有）；另一次整段只罗列证据不给出判定 | 评测集防编造核验捕获 2.51；content-01 关键词率 0 暴露无判定。修复：prompt 禁止任何算术加工；命题判定句改为程序基于证据数字计算后前置，LLM 只写解读（判定即数字的函数，铁律延伸） |
| 8 | LLM 封装按普通聊天模型假设 | deepseek-flash 是推理模型，max_tokens 小了 content 会被 reasoning 吃光为空 | 联调预防性修复：正文只取 content，为空时 max_tokens×2 重试；成本读 usage_metadata |

> 备注：本项目本身就是"用 Kimi 工具链复刻一个迷你版 Kimi 金融方案"——Kimi 金融方案的技能封装 + MCP 数据源 + 合规网关架构被缩小到个人研究者场景验证。
