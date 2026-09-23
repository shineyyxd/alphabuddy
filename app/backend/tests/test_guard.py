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
