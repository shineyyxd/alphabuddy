from app.guard import check_goal


def test_blocks_price_prediction():
    blocked, msg = check_goal("寒武纪下周会涨吗？")
    assert blocked
    assert "涨跌预测" in msg


def test_blocks_buy_advice():
    blocked, msg = check_goal("现在该不该买寒武纪？")
    assert blocked
    assert "买卖建议" in msg


def test_blocks_target_price():
    blocked, _ = check_goal("寒武纪目标价看到多少？")
    assert blocked


def test_allows_research_goal():
    blocked, _ = check_goal("验证寒武纪盈利改善来自主营业务")
    assert not blocked


def test_allows_earnings_review():
    blocked, _ = check_goal("点评寒武纪 2026 中报业绩")
    assert not blocked


def test_blocks_nengmaima_variants():
    for goal in ("宇树科技能买吗", "寒武纪可以买吗", "寒武纪能买么", "宇树科技能入手吗", "寒武纪能入吗"):
        blocked, msg = check_goal(goal)
        assert blocked, goal
        assert "买卖建议" in msg


def test_research_phrasing_not_blocked():
    # 研究型表述含"能"含"盈利"不得误伤
    blocked, _ = check_goal("验证宇树科技的盈利能力")
    assert not blocked
    blocked, _ = check_goal("分析寒武纪能不能持续盈利")
    assert not blocked
