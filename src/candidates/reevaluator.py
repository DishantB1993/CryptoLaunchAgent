from __future__ import annotations

from typing import Any

from src.candidates.tracker import track_candidate_from_score
from src.db import sqlite_storage as dbmod
from src.scoring.launch_score import SCORING_VERSION, score_token


def reevaluate_candidate(db_conn, rpc_manager, candidate: dict[str, Any]) -> dict[str, Any]:
    token_address = candidate["token_address"]
    pair_address = candidate["pair_address"]

    token_data = dbmod.get_token(db_conn, token_address)
    existing_security = dbmod.get_token_security(db_conn, token_address)
    total_supply = token_data.get("total_supply") if token_data else None
    if total_supply is None and existing_security:
        total_supply = existing_security.get("total_supply")

    security = rpc_manager.get_token_security(token_address, total_supply)
    dbmod.save_token_security(
        db_conn,
        token_address,
        security.get("owner_address"),
        security.get("is_ownership_renounced"),
        security.get("total_supply"),
        security.get("owner_balance"),
        security.get("owner_percent"),
        security.get("has_mint_function"),
        security.get("analysis_block"),
        security.get("analysis_ts"),
    )

    liquidity = rpc_manager.get_pair_liquidity(pair_address)
    dbmod.save_pair_liquidity(
        db_conn,
        pair_address,
        liquidity.get("token0"),
        liquidity.get("token1"),
        liquidity.get("reserve0"),
        liquidity.get("reserve1"),
        liquidity.get("block_timestamp_last"),
        liquidity.get("pair_total_supply"),
        liquidity.get("analysis_block"),
        liquidity.get("analysis_ts"),
    )

    token_data = dbmod.get_token(db_conn, token_address)
    security_data = dbmod.get_token_security(db_conn, token_address)
    liquidity_data = dbmod.get_pair_liquidity(db_conn, pair_address)
    score_result = score_token(token_data, security_data, pair_address=pair_address, liquidity=liquidity_data)
    scored_block = security_data.get("analysis_block") or liquidity_data.get("analysis_block")
    score_id = dbmod.save_token_score(
        db_conn,
        token_address,
        pair_address,
        score_result["score"],
        score_result["confidence"],
        score_result["decision"],
        score_result["risk_flags_json"],
        score_result["component_scores_json"],
        score_result["reason"],
        SCORING_VERSION,
        scored_block=scored_block,
    )

    updated_candidate = track_candidate_from_score(
        db_conn,
        token_address,
        pair_address,
        score_id,
        score_result,
        block_number=scored_block,
    )
    return {"candidate": updated_candidate, "score_id": score_id, "score_result": score_result}


def reevaluate_candidates(db_conn, rpc_manager) -> list[dict[str, Any]]:
    results = []
    for candidate in dbmod.list_active_candidates(db_conn):
        results.append(reevaluate_candidate(db_conn, rpc_manager, candidate))
    return results
