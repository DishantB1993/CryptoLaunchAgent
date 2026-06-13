from __future__ import annotations

import json
import time
from typing import Any

from src.db import sqlite_storage as dbmod


ACTIVE_STATUSES = ("candidate", "watchlist", "risky")


def _decode_flags(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        decoded = json.loads(value)
        return decoded if isinstance(decoded, list) else []
    except Exception:
        return []


def list_candidates_with_scores(conn, status: str | None = None) -> list[dict[str, Any]]:
    query = """
        SELECT
            c.token_address,
            c.pair_address,
            c.status,
            c.latest_score_id,
            c.first_seen_block,
            c.first_seen_ts,
            c.created_ts,
            c.updated_ts,
            c.promoted_block,
            c.promoted_ts,
            c.demoted_block,
            c.demoted_ts,
            c.status_reason,
            c.observations_count,
            s.score,
            s.confidence,
            s.decision,
            s.risk_flags,
            s.component_scores,
            s.reason,
            s.scoring_version,
            s.scored_block,
            s.scored_ts
        FROM candidates c
        LEFT JOIN token_scores s ON s.id = c.latest_score_id
    """
    params: list[Any] = []
    if status is not None:
        query += " WHERE c.status = ?"
        params.append(status)
    query += " ORDER BY c.updated_ts DESC, c.token_address ASC"

    cur = conn.cursor()
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    return [
        {
            "token_address": row[0],
            "pair_address": row[1],
            "status": row[2],
            "latest_score_id": row[3],
            "first_seen_block": row[4],
            "first_seen_ts": row[5],
            "created_ts": row[6],
            "updated_ts": row[7],
            "promoted_block": row[8],
            "promoted_ts": row[9],
            "demoted_block": row[10],
            "demoted_ts": row[11],
            "status_reason": row[12],
            "observations_count": row[13],
            "score": row[14],
            "confidence": row[15],
            "decision": row[16],
            "risk_flags": row[17],
            "component_scores": row[18],
            "score_reason": row[19],
            "scoring_version": row[20],
            "scored_block": row[21],
            "scored_ts": row[22],
        }
        for row in rows
    ]


def summarize_candidates(conn) -> dict[str, Any]:
    candidates = list_candidates_with_scores(conn)
    by_status: dict[str, int] = {}
    score_total = 0.0
    confidence_total = 0.0
    scored_count = 0
    for candidate in candidates:
        status = candidate["status"]
        by_status[status] = by_status.get(status, 0) + 1
        if candidate["score"] is not None:
            score_total += float(candidate["score"])
            confidence_total += float(candidate["confidence"] or 0)
            scored_count += 1

    total = len(candidates)
    active_count = sum(by_status.get(status, 0) for status in ACTIVE_STATUSES)
    return {
        "total": total,
        "active": active_count,
        "by_status": by_status,
        "average_score": (score_total / scored_count) if scored_count else None,
        "average_confidence": (confidence_total / scored_count) if scored_count else None,
    }


def summarize_risk_flags(conn) -> dict[str, int]:
    summary: dict[str, int] = {}
    for candidate in list_candidates_with_scores(conn):
        for flag in _decode_flags(candidate.get("risk_flags")):
            summary[flag] = summary.get(flag, 0) + 1
    return dict(sorted(summary.items()))


def find_stale_candidates(conn, now_ts: int | None = None, stale_after_seconds: int = 6 * 60 * 60) -> list[dict[str, Any]]:
    if now_ts is None:
        now_ts = int(time.time())
    return [
        candidate
        for candidate in list_candidates_with_scores(conn)
        if candidate["status"] in ACTIVE_STATUSES
        and candidate["updated_ts"] is not None
        and now_ts - int(candidate["updated_ts"]) >= stale_after_seconds
    ]


def find_expired_candidates(conn, now_ts: int | None = None, expire_after_seconds: int = 24 * 60 * 60) -> list[dict[str, Any]]:
    if now_ts is None:
        now_ts = int(time.time())
    return [
        candidate
        for candidate in list_candidates_with_scores(conn)
        if candidate["status"] in ACTIVE_STATUSES
        and candidate["created_ts"] is not None
        and now_ts - int(candidate["created_ts"]) >= expire_after_seconds
    ]


def expire_candidates(conn, now_ts: int | None = None, expire_after_seconds: int = 24 * 60 * 60, block_number: int = None) -> list[dict[str, Any]]:
    if now_ts is None:
        now_ts = int(time.time())
    expired = []
    for candidate in find_expired_candidates(conn, now_ts=now_ts, expire_after_seconds=expire_after_seconds):
        from_status = candidate["status"]
        reason = "Candidate expired without additional validation."
        updated = dbmod.save_candidate(
            conn,
            candidate["token_address"],
            candidate["pair_address"],
            "expired",
            candidate["latest_score_id"],
            first_seen_block=candidate["first_seen_block"],
            first_seen_ts=candidate["first_seen_ts"],
            block_number=block_number,
            status_reason=reason,
            event_ts=now_ts,
        )
        dbmod.save_candidate_event(
            conn,
            candidate["token_address"],
            candidate["pair_address"],
            "candidate_status_changed",
            from_status=from_status,
            to_status="expired",
            score_id=candidate["latest_score_id"],
            status_reason=reason,
            block_number=block_number,
            event_ts=now_ts,
        )
        expired.append(updated)
    return expired
