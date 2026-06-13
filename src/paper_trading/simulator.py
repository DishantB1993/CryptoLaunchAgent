from __future__ import annotations

import json
import time
from typing import Any

from src.db import sqlite_storage as dbmod


DEFAULT_PAPER_QUANTITY = 1.0
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


def _candidate_id(token_address: str, pair_address: str) -> str:
    return f"{token_address}:{pair_address}"


def _risk_flags(score: dict[str, Any] | None) -> set[str]:
    if not score:
        return set()
    raw = score.get("risk_flags")
    if isinstance(raw, list):
        return set(raw)
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
            return set(decoded) if isinstance(decoded, list) else set()
        except Exception:
            return set()
    return set()


def _entry_allowed(candidate: dict[str, Any], score: dict[str, Any] | None) -> bool:
    if not score:
        return False
    if candidate["status"] != "candidate":
        return False
    if float(score["score"]) < 80 or float(score["confidence"]) < 70:
        return False
    return not (_risk_flags(score) & BLOCKING_FLAGS)


def _exit_reason(candidate: dict[str, Any], score: dict[str, Any] | None) -> str | None:
    if candidate["status"] in ("reject", "risky", "expired"):
        return f"candidate_status_{candidate['status']}"
    blocking = _risk_flags(score) & BLOCKING_FLAGS
    if blocking:
        return "blocking_risk_flag:" + ",".join(sorted(blocking))
    return None


def run_paper_trading_cycle(conn, now_ts: int | None = None, quantity: float = DEFAULT_PAPER_QUANTITY) -> dict[str, list[dict[str, Any]]]:
    if now_ts is None:
        now_ts = int(time.time())

    opened = []
    closed = []

    for position in dbmod.list_open_paper_positions(conn):
        candidate = dbmod.get_candidate(conn, position["token_address"], position["pair_address"])
        score = dbmod.get_latest_token_score(conn, position["token_address"], position["pair_address"])
        if not candidate:
            continue
        reason = _exit_reason(candidate, score)
        if reason is None:
            continue
        dbmod.save_paper_trade(
            conn,
            position["token_address"],
            position["pair_address"],
            _candidate_id(position["token_address"], position["pair_address"]),
            score["id"] if score else position["entry_score_id"],
            "SELL",
            quantity,
            reason,
            created_ts=now_ts,
        )
        closed_position = dbmod.close_paper_position(
            conn,
            position["token_address"],
            position["pair_address"],
            exit_ts=now_ts,
            exit_reason=reason,
        )
        closed.append(closed_position)

    for candidate in dbmod.list_active_candidates(conn):
        if dbmod.get_open_paper_position(conn, candidate["token_address"], candidate["pair_address"]):
            continue
        score = dbmod.get_latest_token_score(conn, candidate["token_address"], candidate["pair_address"])
        if not _entry_allowed(candidate, score):
            continue
        reason = score.get("reason") or "candidate_entry"
        dbmod.save_paper_trade(
            conn,
            candidate["token_address"],
            candidate["pair_address"],
            _candidate_id(candidate["token_address"], candidate["pair_address"]),
            score["id"],
            "BUY",
            quantity,
            reason,
            created_ts=now_ts,
        )
        position = dbmod.save_paper_position(
            conn,
            candidate["token_address"],
            candidate["pair_address"],
            "OPEN",
            score["id"],
            score["score"],
            score["confidence"],
            entry_ts=now_ts,
        )
        opened.append(position)

    return {"opened": opened, "closed": closed}
