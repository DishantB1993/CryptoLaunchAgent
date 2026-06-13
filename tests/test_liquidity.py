from src.liquidity.analyzer import analyze_pair_liquidity


def liquidity_fixture(**overrides):
    liquidity = {
        "reserve0": "1000",
        "reserve1": "2000",
        "block_timestamp_last": 1710000000,
        "pair_total_supply": "100",
        "analysis_block": 123456,
        "analysis_ts": 1710000010,
    }
    liquidity.update(overrides)
    return liquidity


def test_healthy_liquidity_scores_component_without_blocking_flags():
    result = analyze_pair_liquidity(liquidity_fixture())
    assert result["component_score"] == 10
    assert result["risk_flags"] == ["limited_liquidity_signal_set"]
    assert result["caps"] == []


def test_missing_liquidity_is_capped():
    result = analyze_pair_liquidity(None)
    assert "missing_liquidity" in result["risk_flags"]
    assert result["component_score"] == 0
    assert result["caps"] == [70]


def test_unreadable_liquidity_is_capped():
    result = analyze_pair_liquidity(liquidity_fixture(reserve0=None))
    assert "liquidity_unreadable" in result["risk_flags"]
    assert result["caps"] == [70]


def test_zero_reserves_are_capped():
    result = analyze_pair_liquidity(liquidity_fixture(reserve0="0", reserve1="0"))
    assert "zero_reserves" in result["risk_flags"]
    assert 30 in result["caps"]


def test_one_sided_liquidity_is_capped():
    result = analyze_pair_liquidity(liquidity_fixture(reserve0="1000", reserve1="0"))
    assert "one_sided_liquidity" in result["risk_flags"]
    assert 40 in result["caps"]


def test_zero_pair_total_supply_is_capped():
    result = analyze_pair_liquidity(liquidity_fixture(pair_total_supply="0"))
    assert "zero_pair_total_supply" in result["risk_flags"]
    assert 40 in result["caps"]
