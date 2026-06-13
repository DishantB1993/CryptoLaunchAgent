import json

from src.candidates.analytics import (
    expire_candidates,
    find_expired_candidates,
    find_stale_candidates,
    list_candidates_with_scores,
    summarize_candidates,
    summarize_risk_flags,
)
from src.db import sqlite_storage as dbmod


def add_candidate(conn, token, pair, status, score, confidence, flags, created_ts, updated_ts=None):
    if updated_ts is None:
        updated_ts = created_ts
    score_id = dbmod.save_token_score(
        conn,
        token,
        pair,
        score,
        confidence,
        status if status != "expired" else "candidate",
        json.dumps(flags),
        json.dumps({"ownership": 20}),
        "test reason",
        "launch_score_v1",
        scored_block=100,
        scored_ts=created_ts,
    )
    candidate = dbmod.save_candidate(
        conn,
        token,
        pair,
        status,
        score_id,
        first_seen_block=100,
        block_number=100,
        status_reason="test reason",
        event_ts=created_ts,
    )
    if updated_ts != created_ts:
        conn.execute(
            "UPDATE candidates SET updated_ts = ? WHERE token_address = ? AND pair_address = ?",
            (updated_ts, token, pair),
        )
        conn.commit()
        candidate = dbmod.get_candidate(conn, token, pair)
    return candidate


def test_list_candidates_with_scores_joins_latest_score():
    conn = dbmod.init_db(":memory:")
    add_candidate(conn, "0xA", "0xP", "candidate", 90.0, 90.0, ["limited_v1_signal_set"], 1000)
    rows = list_candidates_with_scores(conn)
    assert len(rows) == 1
    assert rows[0]["token_address"] == "0xA"
    assert rows[0]["status"] == "candidate"
    assert rows[0]["score"] == 90.0
    assert rows[0]["confidence"] == 90.0


def test_summarize_candidates_counts_statuses_and_averages_scores():
    conn = dbmod.init_db(":memory:")
    add_candidate(conn, "0xA", "0xP", "candidate", 90.0, 90.0, ["limited_v1_signal_set"], 1000)
    add_candidate(conn, "0xB", "0xQ", "reject", 35.0, 5.0, ["missing_security"], 1001)
    summary = summarize_candidates(conn)
    assert summary["total"] == 2
    assert summary["active"] == 1
    assert summary["by_status"] == {"candidate": 1, "reject": 1}
    assert summary["average_score"] == 62.5
    assert summary["average_confidence"] == 47.5


def test_summarize_risk_flags_counts_latest_candidate_flags():
    conn = dbmod.init_db(":memory:")
    add_candidate(conn, "0xA", "0xP", "candidate", 90.0, 90.0, ["limited_v1_signal_set"], 1000)
    add_candidate(conn, "0xB", "0xQ", "reject", 50.0, 90.0, ["limited_v1_signal_set", "mint_function_detected"], 1001)
    summary = summarize_risk_flags(conn)
    assert summary["limited_v1_signal_set"] == 2
    assert summary["mint_function_detected"] == 1


def test_find_stale_candidates_uses_updated_timestamp():
    conn = dbmod.init_db(":memory:")
    add_candidate(conn, "0xA", "0xP", "candidate", 90.0, 90.0, ["limited_v1_signal_set"], 1000, updated_ts=1000)
    add_candidate(conn, "0xB", "0xQ", "candidate", 90.0, 90.0, ["limited_v1_signal_set"], 2000, updated_ts=1900)
    stale = find_stale_candidates(conn, now_ts=2000, stale_after_seconds=500)
    assert [row["token_address"] for row in stale] == ["0xA"]


def test_find_expired_candidates_uses_created_timestamp():
    conn = dbmod.init_db(":memory:")
    add_candidate(conn, "0xA", "0xP", "candidate", 90.0, 90.0, ["limited_v1_signal_set"], 1000)
    add_candidate(conn, "0xB", "0xQ", "candidate", 90.0, 90.0, ["limited_v1_signal_set"], 1900)
    expired = find_expired_candidates(conn, now_ts=2000, expire_after_seconds=500)
    assert [row["token_address"] for row in expired] == ["0xA"]


def test_expire_candidates_updates_status_and_writes_event():
    conn = dbmod.init_db(":memory:")
    add_candidate(conn, "0xA", "0xP", "candidate", 90.0, 90.0, ["limited_v1_signal_set"], 1000)
    expired = expire_candidates(conn, now_ts=2000, expire_after_seconds=500, block_number=150)
    assert len(expired) == 1
    candidate = dbmod.get_candidate(conn, "0xA", "0xP")
    assert candidate["status"] == "expired"
    assert candidate["demoted_block"] == 150
    assert candidate["demoted_ts"] == 2000
    cur = conn.cursor()
    cur.execute("SELECT event_type, from_status, to_status, block_number FROM candidate_events")
    event = cur.fetchone()
    assert event[0] == "candidate_status_changed"
    assert event[1] == "candidate"
    assert event[2] == "expired"
    assert event[3] == 150
