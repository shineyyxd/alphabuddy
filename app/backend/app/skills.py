from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SkillCard:
    name: str
    display_name: str
    description: str
    keywords: tuple[str, ...]
    tool_whitelist: tuple[str, ...]
    plan_steps: tuple[tuple[str, str], ...] = field(default=())  # (title, tool)


SKILLS: dict[str, SkillCard] = {
    "thesis_check": SkillCard(
        name="thesis_check",
        display_name="命题验证",
        description="验证一句投资说法：取数 → 交叉核验 → 给出证据与待核实事项",
        keywords=("验证", "命题", "说法", "是否属实", "求证", "是否来自"),
        tool_whitelist=(
            "fuyao_quote_snapshot", "fuyao_valuation",
            "ifind_fin_indicator", "ifind_fin_statement", "ifind_announcement",
        ),
        plan_steps=(
            ("获取行情快照", "fuyao_quote_snapshot"),
            ("获取财务指标（本期 vs 上年同期）", "ifind_fin_indicator"),
            ("获取利润表，拆解收入/利润结构", "ifind_fin_statement"),
            ("获取公告线索，定位原始披露材料", "ifind_announcement"),
        ),
    ),
    "earnings_review": SkillCard(
        name="earnings_review",
        display_name="业绩点评",
        description="读最新财报：增长/盈利/费用/减值四段式点评",
        keywords=("业绩", "财报", "点评", "季报", "年报", "中报"),
        tool_whitelist=(
            "ifind_fin_indicator", "ifind_fin_statement",
            "fuyao_valuation", "ifind_announcement",
        ),
        plan_steps=(
            ("获取财务指标（增长/盈利/费用）", "ifind_fin_indicator"),
            ("获取利润表（减值/非经常项）", "ifind_fin_statement"),
            ("获取估值快照", "fuyao_valuation"),
            ("获取公告线索", "ifind_announcement"),
        ),
    ),
    "watchlist_brief": SkillCard(
        name="watchlist_brief",
        display_name="持仓早报",
        description="对自选标的跑例行扫描：行情 + 估值 + 公告",
        keywords=("早报", "持仓", "自选", "扫描", "盯盘"),
        tool_whitelist=("fuyao_quote_snapshot", "fuyao_valuation", "ifind_announcement"),
        plan_steps=(
            ("获取行情快照", "fuyao_quote_snapshot"),
            ("获取估值快照", "fuyao_valuation"),
            ("获取最新公告", "ifind_announcement"),
        ),
    ),
}

ALIASES = {
    "寒武纪": "688256.SH",
    "贵州茅台": "600519.SH",
    "茅台": "600519.SH",
}

DEFAULT_REPORT = "2026-2"  # 最新已披露报告期：2026 中报


def match_skill(goal: str) -> str:
    for name, card in SKILLS.items():
        if any(k in goal for k in card.keywords):
            return name
    return "thesis_check"
