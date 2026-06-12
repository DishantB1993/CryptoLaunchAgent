import json

from src.candidates.tracker import classify_candidate, track_candidate_from_score
from src.db import sqlite_storage as dbmod


def score_result(**overrides):
    result = {
        "score": 90.0,
        "confidence": 90.0,
        "decision": "candidate",
        "risk_flags": ["limited_v1_signal_set"],
        "reason": "No v1 risk flags detected; limited checks only.",
        "risk_flags_json": json.dumps(["limited_v1_signal_set"]),
        "component_scores_json": json.dumps({"ownership": 20}),
    }
    result.update(overrides)
    return result


def save_score(conn, result):
    return dbmod.save_token_score(
        conn,
        "0xT",
        "0xP",
        result["score"],
        result["confidence"],
        result["decision"],
        result.get("risk_flags_json", json.dumps(result["risk_flags"])),
        result["component_scores_json"],
        result["reason"],
        "launch_score_v1",
        scored_block=123,
        scored_ts=1710000000,
    )


def test_candidate_creation():
    conn = dbmod.init_db(":memory:")
    result = score_result()
    score_id = save_score(conn, result)
    candidate = track_candidate_from_score(conn, "0xT", "0xP", score_id, result, block_number=123, event_ts=1710000000)
    assert candidate["status"] == "candidate"
    assert candidate["latest_score_id"] == score_id
    assert candidate["observations_count"] == 1


def test_watchlist_creation():
    result = score_result(score=70.0, confidence=75.0, decision="watchlist", reason="Watchlist threshold met.")
    status, reason = classify_candidate(result)
    assert status == "watchlist"
    assert reason == "Watchlist threshold met."


def test_rejection_for_mint_risk():
    result = score_result(
        score=50.0,
        decision="risky",
        risk_flags=["limited_v1_signal_set", "mint_function_detected"],
        risk_flags_json=json.dumps(["limited_v1_signal_set", "mint_function_detected"]),
        reason="Mint function detected; score capped.",
    )
    status, reason = classify_candidate(result)
    assert status == "reject"
    assert reason == "Mint function detected; score capped."


def test_rejection_for_missing_security():
    result = score_result(
        score=32.0,
        confidence=5.0,
        decision="reject",
        risk_flags=["limited_v1_signal_set", "missing_security"],
        risk_flags_json=json.dumps(["limited_v1_signal_set", "missing_security"]),
        reason="Security analysis incomplete.",
    )
    status, reason = classify_candidate(result)
    assert status == "reject"
    assert reason == "Security analysis incomplete."


def test_candidate_event_creation():
    conn = dbmod.init_db(":memory:")
    result = score_result()
    score_id = save_score(conn, result)
    track_candidate_from_score(conn, "0xT", "0xP", score_id, result, block_number=123, event_ts=1710000000)
    cur = conn.cursor()
    cur.execute("SELECT event_type, from_status, to_status, score_id FROM candidate_events")
    row = cur.fetchone()
    assert row[0] == "candidate_created"
    assert row[1] is None
    assert row[2] == "candidate"
    assert row[3] == score_id
