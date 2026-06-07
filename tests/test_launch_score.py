import json

from src.scoring.launch_score import SCORING_VERSION, candidate_tokens, is_base_token, score_token


WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
USDT = "0x55d398326f99059fF775485246999027B3197955"
NEW_TOKEN = "0x1111111111111111111111111111111111111111"
OTHER_TOKEN = "0x2222222222222222222222222222222222222222"


def token_fixture():
    return {
        "token_address": NEW_TOKEN,
        "name": "Launch Token",
        "symbol": "LAUNCH",
        "decimals": 18,
        "total_supply": "1000000",
        "first_seen_block": 100,
        "first_seen_ts": 1710000000,
    }


def security_fixture(**overrides):
    security = {
        "token_address": NEW_TOKEN,
        "owner_address": "0x3333333333333333333333333333333333333333",
        "is_ownership_renounced": True,
        "total_supply": "1000000",
        "owner_balance": "1000",
        "owner_percent": 0.1,
        "has_mint_function": False,
        "analysis_block": 101,
        "analysis_ts": 1710000010,
    }
    security.update(overrides)
    return security


def test_base_token_filtering():
    assert is_base_token(WBNB)
    assert candidate_tokens(WBNB, NEW_TOKEN) == [NEW_TOKEN]
    assert candidate_tokens(NEW_TOKEN, USDT) == [NEW_TOKEN]
    assert candidate_tokens(WBNB, USDT) == []
    assert candidate_tokens(NEW_TOKEN, OTHER_TOKEN) == [NEW_TOKEN, OTHER_TOKEN]


def test_high_quality_token_scores_as_candidate():
    result = score_token(token_fixture(), security_fixture(), pair_address="0xPair")
    assert result["scoring_version"] == SCORING_VERSION
    assert result["score"] == 90.0
    assert result["confidence"] == 90.0
    assert result["decision"] == "candidate"
    assert result["risk_flags"] == ["limited_v1_signal_set"]
    assert result["reason"] == "No v1 risk flags detected; limited checks only."
    assert json.loads(result["component_scores_json"])["mint"] == 15
    assert json.loads(result["component_scores_json"])["metadata"] == 15
    assert json.loads(result["component_scores_json"])["owner_concentration"] == 35


def test_mint_function_caps_score_and_adds_risk_flag():
    result = score_token(token_fixture(), security_fixture(has_mint_function=True), pair_address="0xPair")
    assert result["score"] <= 50
    assert result["confidence"] == 90.0
    assert result["decision"] in {"risky", "reject"}
    assert "mint_function_detected" in result["risk_flags"]
    assert "limited_v1_signal_set" in result["risk_flags"]
    assert result["reason"] == "Mint function detected; score capped."


def test_missing_security_lowers_confidence_and_score_cap():
    result = score_token(token_fixture(), None, pair_address="0xPair")
    assert result["score"] <= 35
    assert result["confidence"] == 5.0
    assert "missing_security" in result["risk_flags"]
    assert "missing_owner" in result["risk_flags"]
    assert "limited_v1_signal_set" in result["risk_flags"]
    assert result["reason"] == "Security analysis incomplete."


def test_high_owner_concentration_caps_score():
    result = score_token(token_fixture(), security_fixture(owner_percent=85.0), pair_address="0xPair")
    assert result["score"] <= 25
    assert result["decision"] == "reject"
    assert "severe_owner_concentration" in result["risk_flags"]
    assert result["reason"] == "Owner controls more than 80% of supply."


def test_owner_percent_above_50_caps_score():
    result = score_token(token_fixture(), security_fixture(owner_percent=60.0), pair_address="0xPair")
    assert result["score"] <= 40
    assert result["decision"] in {"risky", "reject"}
    assert "high_owner_concentration" in result["risk_flags"]
    assert result["reason"] == "Owner controls more than 50% of supply."


def test_owner_not_renounced_and_unknown_owner_percent_caps_score():
    result = score_token(
        token_fixture(),
        security_fixture(is_ownership_renounced=False, owner_percent=None),
        pair_address="0xPair",
    )
    assert result["score"] <= 55
    assert result["confidence"] == 85.0
    assert "owner_not_renounced_and_owner_percent_unknown" in result["risk_flags"]
    assert result["reason"] == "Ownership is not renounced and owner concentration is unknown."


def test_missing_total_supply_caps_score_and_reduces_confidence():
    token = token_fixture()
    token["total_supply"] = None
    result = score_token(token, security_fixture(total_supply=None), pair_address="0xPair")
    assert result["score"] <= 65
    assert result["confidence"] == 90.0
    assert "missing_total_supply" in result["risk_flags"]
    assert result["reason"] == "Total supply unavailable."


def test_missing_analysis_timing_reduces_confidence():
    result = score_token(
        token_fixture(),
        security_fixture(analysis_block=None, analysis_ts=None),
        pair_address="0xPair",
    )
    assert result["confidence"] == 90.0
    assert "missing_analysis_block" in result["risk_flags"]
    assert "missing_analysis_ts" in result["risk_flags"]


def test_v1_caps_apply_to_otherwise_perfect_candidate():
    result = score_token(token_fixture(), security_fixture(), pair_address="0xPair")
    assert result["score"] == 90.0
    assert result["confidence"] == 90.0
    assert result["decision"] == "candidate"
    assert "limited_v1_signal_set" in result["risk_flags"]
