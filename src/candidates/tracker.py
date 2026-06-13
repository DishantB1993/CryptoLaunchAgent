from __future__ import annotations

import json
from typing import Any

from src.db import sqlite_storage as dbmod


ACTIVE_STATUSES = ("candidate", "watchlist", "risky")
VALID_STATUSES = ACTIVE_STATUSES + ("reject", "expired")
BLOCKING_FLAGS = {
    "mint_function_detected",
    "high_owner_concentration",
    "severe_owner_concentration",
    "missing_security",
    "liquidity_unreadable",
    "zero_reserves",
    "one_sided_liquidity",
    "zero_pair_total_supply",
}


def _risk_flags(score_result: dict[str, Any]) -> list[str]:
    flags = score_result.get("risk_flags")
    if isinstance(flags, list):
        return flags
    if isinstance(flags, str):
        try:
            decoded = json.loads(flags)
            return decoded if isinstance(decoded, list) else []
        except Exception:
            return []
    return []


def classify_candidate(score_result: dict[str, Any]) -> tuple[str, str]:
    score = float(score_result.get("score") or 0)
    confidence = float(score_result.get("confidence") or 0)
    decision = score_result.get("decision")
    flags = set(_risk_flags(score_result))

    if flags & BLOCKING_FLAGS:
        return "reject", score_result.get("reason") or "Blocking v1 risk flag detected."
    if decision == "candidate" and score >= 80 and confidence >= 70:
        return "candidate", score_result.get("reason") or "Candidate threshold met."
    if decision == "watchlist" and score >= 65 and confidence >= 60:
        return "watchlist", score_result.get("reason") or "Watchlist threshold met."
    if decision == "reject" or score < 40:
        return "reject", score_result.get("reason") or "Rejected by v1 score."
    return "risky", score_result.get("reason") or "Risky v1 score band."


def track_candidate_from_score(
    conn,
    token_address: str,
    pair_address: str,
    score_id: int,
    score_result: dict[str, Any],
    block_number: int = None,
    event_ts: int = None,
):
    status, status_reason = classify_candidate(score_result)
    existing = dbmod.get_candidate(conn, token_address, pair_address)
    from_status = existing["status"] if existing else None

    candidate = dbmod.save_candidate(
        conn,
        token_address,
        pair_address,
        status,
        score_id,
        first_seen_block=block_number,
        block_number=block_number,
        status_reason=status_reason,
        event_ts=event_ts,
    )

    if not existing:
        event_type = "candidate_created"
    elif from_status != status:
        event_type = "candidate_status_changed"
    else:
        return candidate

    dbmod.save_candidate_event(
        conn,
        token_address,
        pair_address,
        event_type,
        from_status=from_status,
        to_status=status,
        score_id=score_id,
        status_reason=status_reason,
        block_number=block_number,
        event_ts=event_ts,
    )
    return candidate
