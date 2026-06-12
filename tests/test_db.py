import os
import json
import sqlite3
import tempfile
from src.db import sqlite_storage as dbmod


def test_db_init_and_meta():
    fd, path = tempfile.mkstemp(prefix="test_db_", suffix=".sqlite3")
    os.close(fd)
    conn = dbmod.init_db(path)
    assert conn is not None
    # last_block initially None
    assert dbmod.get_last_block(conn) is None
    dbmod.set_last_block(conn, 12345)
    assert dbmod.get_last_block(conn) == 12345
    # chain id
    assert dbmod.get_chain_id(conn) is None
    dbmod.set_chain_id(conn, 56)
    assert dbmod.get_chain_id(conn) == 56
    # rpc health rows
    dbmod.init_rpc_health_rows(conn, ["https://rpc1", "https://rpc2"])
    h = dbmod.get_rpc_health(conn, "https://rpc1")
    assert h is not None
    # save pair and dedupe
    dbmod.save_pair(conn, "0xPP", "0xT0", "0xT1", "0xF", "0xTX", 100)
    dbmod.save_pair(conn, "0xPP", "0xT0", "0xT1", "0xF", "0xTX", 100)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM pairs WHERE pair_address = ?", ("0xPP",))
    row = cur.fetchone()
    assert row[0] == 1
    conn.close()
    os.remove(path)


def test_legacy_token_security_migration_adds_timing_columns():
    fd, path = tempfile.mkstemp(prefix="test_db_", suffix=".sqlite3")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE token_security (
            token_address TEXT PRIMARY KEY,
            owner_address TEXT,
            is_ownership_renounced INTEGER,
            total_supply TEXT,
            owner_balance TEXT,
            owner_percent REAL,
            has_mint_function INTEGER
        )
        """
    )
    conn.commit()
    conn.close()

    conn = dbmod.init_db(path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(token_security)")
    columns = {row[1] for row in cur.fetchall()}
    assert "analysis_block" in columns
    assert "analysis_ts" in columns
    conn.close()
    os.remove(path)


def test_save_token_security_persists_analysis_timing():
    fd, path = tempfile.mkstemp(prefix="test_db_", suffix=".sqlite3")
    os.close(fd)
    conn = dbmod.init_db(path)
    dbmod.save_token_security(
        conn,
        "0xT",
        "0xOwner",
        False,
        "1000",
        "100",
        10.0,
        False,
        analysis_block=123456,
        analysis_ts=1710000000,
    )
    security = dbmod.get_token_security(conn, "0xT")
    assert security["analysis_block"] == 123456
    assert security["analysis_ts"] == 1710000000
    conn.close()
    os.remove(path)


def test_save_and_get_latest_token_score():
    fd, path = tempfile.mkstemp(prefix="test_db_", suffix=".sqlite3")
    os.close(fd)
    conn = dbmod.init_db(path)
    dbmod.save_token_score(
        conn,
        "0xT",
        "0xP",
        82.0,
        90.0,
        "candidate",
        json.dumps(["ownership_not_renounced"]),
        json.dumps({"ownership": 10}),
        "candidate: ownership_not_renounced",
        "launch_score_v1",
        scored_block=123456,
        scored_ts=1710000000,
    )
    score = dbmod.get_latest_token_score(conn, "0xT", "0xP", "launch_score_v1")
    assert score["token_address"] == "0xT"
    assert score["pair_address"] == "0xP"
    assert score["score"] == 82.0
    assert score["confidence"] == 90.0
    assert score["decision"] == "candidate"
    assert json.loads(score["risk_flags"]) == ["ownership_not_renounced"]
    assert json.loads(score["component_scores"]) == {"ownership": 10}
    assert score["reason"] == "candidate: ownership_not_renounced"
    assert score["scoring_version"] == "launch_score_v1"
    assert score["scored_block"] == 123456
    assert score["scored_ts"] == 1710000000
    conn.close()
    os.remove(path)


def test_candidate_tables_are_created():
    fd, path = tempfile.mkstemp(prefix="test_db_", suffix=".sqlite3")
    os.close(fd)
    conn = dbmod.init_db(path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cur.fetchall()}
    assert "candidates" in tables
    assert "candidate_events" in tables
    conn.close()
    os.remove(path)


def test_save_candidate_and_event_helpers():
    fd, path = tempfile.mkstemp(prefix="test_db_", suffix=".sqlite3")
    os.close(fd)
    conn = dbmod.init_db(path)
    score_id = dbmod.save_token_score(
        conn,
        "0xT",
        "0xP",
        90.0,
        90.0,
        "candidate",
        json.dumps(["limited_v1_signal_set"]),
        json.dumps({"ownership": 20}),
        "No v1 risk flags detected; limited checks only.",
        "launch_score_v1",
        scored_block=123,
        scored_ts=1710000000,
    )
    candidate = dbmod.save_candidate(
        conn,
        "0xT",
        "0xP",
        "candidate",
        score_id,
        first_seen_block=123,
        block_number=123,
        status_reason="No v1 risk flags detected; limited checks only.",
        event_ts=1710000000,
    )
    assert candidate["status"] == "candidate"
    assert candidate["latest_score_id"] == score_id
    assert candidate["promoted_block"] == 123
    event_id = dbmod.save_candidate_event(
        conn,
        "0xT",
        "0xP",
        "candidate_created",
        to_status="candidate",
        score_id=score_id,
        block_number=123,
        event_ts=1710000000,
    )
    assert event_id is not None
    active = dbmod.list_active_candidates(conn)
    assert len(active) == 1
    assert active[0]["token_address"] == "0xT"
    conn.close()
    os.remove(path)
