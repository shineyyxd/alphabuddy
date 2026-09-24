from __future__ import annotations

import re

# 涨跌预测 / 买卖建议类意图 —— 命中即拦截，不进入 Agent 图
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"会涨吗|会跌吗|涨不涨|跌不跌|能涨多少|会涨到|会跌到"), "涨跌预测"),
    (re.compile(r"该不该买|该不该卖|要不要买|要不要卖|能不能买|能不能卖|可以买入|可以卖出"), "买卖建议"),
    (re.compile(r"能买[吗么]|可以买[吗么]|可买[吗么]|能入手[吗么]|能入[吗么]|可入[吗么]|值得入手[吗么]"), "买卖建议"),
    (re.compile(r"建议买|建议卖|推荐买|推荐买|买入建议|卖出建议|值得买吗|值得入手"), "买卖建议"),
    (re.compile(r"目标价|看到多少[块元]|能到多少[块元]"), "涨跌预测"),
    (re.compile(r"满仓|空仓|加仓|减仓|抄底|逃顶|止损位|买点|卖点"), "择时/仓位建议"),
]

GUIDANCE = (
    "本产品仅做事实研究，不提供涨跌预测或买卖建议。你可以把问题改写为可验证的研究目标，"
    "例如：「验证 XX 盈利改善是否来自主营业务」「点评 XX 最新一期财报的增长/盈利/费用/减值」。"
)


def check_goal(goal: str) -> tuple[bool, str]:
    """返回 (blocked, message)。命中合规红线时 blocked=True 并给出引导话术。"""
    for pattern, kind in _PATTERNS:
        if pattern.search(goal):
            return True, f"输入涉及「{kind}」类意图，已拦截。{GUIDANCE}"
    return False, ""
