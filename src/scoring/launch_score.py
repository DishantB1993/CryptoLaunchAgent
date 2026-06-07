from __future__ import annotations

import json
from typing import Any


SCORING_VERSION = "launch_score_v1"
MAX_SCORE_V1 = 90
MAX_CONFIDENCE_V1 = 90
LIMITED_V1_SIGNAL_FLAG = "limited_v1_signal_set"

BASE_TOKEN_ADDRESSES = {
    # WBNB
    "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",
    # USDT
    "0x55d398326f99059ff775485246999027b3197955",
    # USDC
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",
    # BUSD
    "0xe9e7cea3dedca5984780bafc599bd69add087d56",
    # DAI
    "0x1af3f329e8be154074d8769d1ffa4ee058b1dbc3",
    # CAKE
    "0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82",
}


def _norm_addr(address: str | None) -> str:
    return address.lower() if isinstance(address, str) else ""


def is_base_token(address: str | None) -> bool:
    return _norm_addr(address) in BASE_TOKEN_ADDRESSES


def candidate_tokens(token0: str | None, token1: str | None) -> list[str]:
    token0_is_base = is_base_token(token0)
    token1_is_base = is_base_token(token1)
    candidates = []
    if token0 and not token0_is_base:
        candidates.append(token0)
    if token1 and not token1_is_base:
        candidates.append(token1)
    return candidates


def _positive_int(value: Any) -> bool:
    try:
        return int(value) > 0
    except Exception:
        return False


def _valid_decimals(value: Any) -> bool:
    try:
        decimals = int(value)
        return 0 <= decimals <= 30
    except Exception:
        return False


def _decision(score: float) -> str:
    if score >= 80:
        return "candidate"
    if score >= 65:
        return "watchlist"
    if score >= 40:
        return "risky"
    return "reject"


def _reason(decision: str, risk_flags: list[str]) -> str:
    if "mint_function_detected" in risk_flags:
        return "Mint function detected; score capped."
    if "severe_owner_concentration" in risk_flags:
        return "Owner controls more than 80% of supply."
    if "high_owner_concentration" in risk_flags:
        return "Owner controls more than 50% of supply."
    if "missing_security" in risk_flags:
        return "Security analysis incomplete."
    if "missing_total_supply" in risk_flags:
        return "Total supply unavailable."
    if "owner_not_renounced_and_owner_percent_unknown" in risk_flags:
        return "Ownership is not renounced and owner concentration is unknown."
    if "ownership_not_renounced" in risk_flags:
        return "Ownership is not renounced."
    material_flags = [flag for flag in risk_flags if flag != LIMITED_V1_SIGNAL_FLAG]
    if not material_flags and decision == "candidate":
        return "No v1 risk flags detected; limited checks only."
    if risk_flags:
        return "; ".join(material_flags[:3] or risk_flags[:3]).replace("_", " ").capitalize() + "."
    return decision


def score_token(token: dict | None, security: dict | None, pair_address: str | None = None) -> dict:
    risk_flags: list[str] = [LIMITED_V1_SIGNAL_FLAG]
    component_scores = {
        "ownership": 0,
        "owner_concentration": 0,
        "mint": 0,
        "metadata": 0,
        "timing": 0,
    }

    if token is None:
        token = {}
        risk_flags.append("missing_token_metadata")

    if security is None:
        security = {}
        risk_flags.append("missing_security")

    if security.get("is_ownership_renounced") is True:
        component_scores["ownership"] = 20
    elif security.get("owner_address"):
        component_scores["ownership"] = 8
        risk_flags.append("ownership_not_renounced")
    else:
        component_scores["ownership"] = 4
        risk_flags.append("missing_owner")

    owner_percent = security.get("owner_percent")
    if owner_percent is None:
        component_scores["owner_concentration"] = 5
        risk_flags.append("missing_owner_percent")
    elif owner_percent <= 1:
        component_scores["owner_concentration"] = 35
    elif owner_percent <= 5:
        component_scores["owner_concentration"] = 28
    elif owner_percent <= 10:
        component_scores["owner_concentration"] = 20
    elif owner_percent <= 20:
        component_scores["owner_concentration"] = 12
    elif owner_percent <= 50:
        component_scores["owner_concentration"] = 5
        risk_flags.append("elevated_owner_concentration")
    else:
        component_scores["owner_concentration"] = 0
        risk_flags.append("high_owner_concentration")
        if owner_percent > 80:
            risk_flags.append("severe_owner_concentration")

    has_mint = security.get("has_mint_function")
    if has_mint is True:
        component_scores["mint"] = 0
        risk_flags.append("mint_function_detected")
    elif has_mint is False:
        component_scores["mint"] = 15
    else:
        component_scores["mint"] = 5
        risk_flags.append("missing_mint_status")

    if token.get("name"):
        component_scores["metadata"] += 3
    else:
        risk_flags.append("missing_name")
    if token.get("symbol"):
        component_scores["metadata"] += 3
    else:
        risk_flags.append("missing_symbol")
    if _valid_decimals(token.get("decimals")):
        component_scores["metadata"] += 3
    else:
        risk_flags.append("missing_or_invalid_decimals")
    if _positive_int(token.get("total_supply") or security.get("total_supply")):
        component_scores["metadata"] += 4
    else:
        risk_flags.append("missing_total_supply")
    if token.get("first_seen_block") is not None:
        component_scores["metadata"] += 2
    else:
        risk_flags.append("missing_first_seen_block")

    if security.get("analysis_block") is not None:
        component_scores["timing"] += 7
    else:
        risk_flags.append("missing_analysis_block")
    if security.get("analysis_ts") is not None:
        component_scores["timing"] += 5
    else:
        risk_flags.append("missing_analysis_ts")
    if pair_address:
        component_scores["timing"] += 3
    else:
        risk_flags.append("missing_pair_address")

    score = float(sum(component_scores.values()))
    caps = []
    if has_mint is True:
        caps.append(50)
    if owner_percent is not None and owner_percent > 50:
        caps.append(40)
    if owner_percent is not None and owner_percent > 80:
        caps.append(25)
    if security.get("owner_address") and security.get("is_ownership_renounced") is not True and owner_percent is None:
        caps.append(55)
        risk_flags.append("owner_not_renounced_and_owner_percent_unknown")
    if "missing_security" in risk_flags:
        caps.append(35)
    if "missing_total_supply" in risk_flags:
        caps.append(65)
    if caps:
        score = min(score, min(caps))
    score = min(score, MAX_SCORE_V1)

    confidence = 100.0
    confidence -= 40 if "missing_security" in risk_flags else 0
    confidence -= 15 if "missing_owner" in risk_flags else 0
    confidence -= 15 if "missing_owner_percent" in risk_flags else 0
    confidence -= 15 if "missing_mint_status" in risk_flags else 0
    confidence -= 10 if "missing_total_supply" in risk_flags else 0
    confidence -= 5 if "missing_analysis_block" in risk_flags else 0
    confidence -= 5 if "missing_analysis_ts" in risk_flags else 0
    confidence = max(0.0, min(MAX_CONFIDENCE_V1, confidence))

    decision = _decision(score)
    reason = _reason(decision, risk_flags)

    return {
        "score": score,
        "confidence": confidence,
        "decision": decision,
        "risk_flags": risk_flags,
        "component_scores": component_scores,
        "reason": reason,
        "scoring_version": SCORING_VERSION,
        "risk_flags_json": json.dumps(risk_flags, sort_keys=True),
        "component_scores_json": json.dumps(component_scores, sort_keys=True),
    }
