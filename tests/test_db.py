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


def test_save_and_get_pair_liquidity():
    fd, path = tempfile.mkstemp(prefix="test_db_", suffix=".sqlite3")
    os.close(fd)
    conn = dbmod.init_db(path)
    dbmod.save_pair_liquidity(
        conn,
        "0xP",
        "0xT0",
        "0xT1",
        "1000",
        "2000",
        1710000000,
        "100",
        123456,
        1710000010,
    )
    liquidity = dbmod.get_pair_liquidity(conn, "0xP")
    assert liquidity["pair_address"] == "0xP"
    assert liquidity["token0"] == "0xT0"
    assert liquidity["token1"] == "0xT1"
    assert liquidity["reserve0"] == "1000"
    assert liquidity["reserve1"] == "2000"
    assert liquidity["block_timestamp_last"] == 1710000000
    assert liquidity["pair_total_supply"] == "100"
    assert liquidity["analysis_block"] == 123456
    assert liquidity["analysis_ts"] == 1710000010
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


def test_token_scores_migration_removes_legacy_unique_constraint_and_preserves_rows():
    fd, path = tempfile.mkstemp(prefix="test_db_", suffix=".sqlite3")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE token_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT NOT NULL,
            pair_address TEXT,
            score REAL NOT NULL,
            confidence REAL NOT NULL,
            decision TEXT NOT NULL,
            risk_flags TEXT,
            component_scores TEXT,
            reason TEXT,
            scoring_version TEXT NOT NULL,
            scored_block INTEGER,
            scored_ts INTEGER NOT NULL,
            UNIQUE(token_address, pair_address, scoring_version)
        )
        """
    )
    conn.execute(
        "INSERT INTO token_scores(token_address,pair_address,score,confidence,decision,risk_flags,component_scores,reason,scoring_version,scored_block,scored_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        ("0xT", "0xP", 70.0, 80.0, "watchlist", "[]", "{}", "old score", "launch_score_v1", 100, 1710000000),
    )
    conn.commit()
    conn.close()

    conn = dbmod.init_db(path)
    first = dbmod.get_latest_token_score(conn, "0xT", "0xP", "launch_score_v1")
    assert first["score"] == 70.0
    second_id = dbmod.save_token_score(
        conn,
        "0xT",
        "0xP",
        90.0,
        90.0,
        "candidate",
        "[]",
        "{}",
        "new score",
        "launch_score_v1",
        scored_block=101,
        scored_ts=1710000100,
    )
    assert second_id != first["id"]
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM token_scores WHERE token_address = ? AND pair_address = ?", ("0xT", "0xP"))
    assert cur.fetchone()[0] == 2
    cur.execute("PRAGMA index_list(token_scores)")
    unique_indexes = [row for row in cur.fetchall() if row[2]]
    assert unique_indexes == []
    conn.close()
    os.remove(path)


def test_multiple_token_scores_are_append_only_and_latest_score_wins():
    fd, path = tempfile.mkstemp(prefix="test_db_", suffix=".sqlite3")
    os.close(fd)
    conn = dbmod.init_db(path)
    first_id = dbmod.save_token_score(
        conn,
        "0xT",
        "0xP",
        65.0,
        70.0,
        "watchlist",
        "[]",
        "{}",
        "first",
        "launch_score_v1",
        scored_block=100,
        scored_ts=1710000000,
    )
    second_id = dbmod.save_token_score(
        conn,
        "0xT",
        "0xP",
        90.0,
        90.0,
        "candidate",
        "[]",
        "{}",
        "second",
        "launch_score_v1",
        scored_block=101,
        scored_ts=1710000100,
    )
    latest = dbmod.get_latest_token_score(conn, "0xT", "0xP", "launch_score_v1")
    assert first_id != second_id
    assert latest["id"] == second_id
    assert latest["score"] == 90.0
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM token_scores WHERE token_address = ? AND pair_address = ?", ("0xT", "0xP"))
    assert cur.fetchone()[0] == 2
    conn.close()
    os.remove(path)


def test_candidate_latest_score_id_can_reference_newest_score():
    fd, path = tempfile.mkstemp(prefix="test_db_", suffix=".sqlite3")
    os.close(fd)
    conn = dbmod.init_db(path)
    first_id = dbmod.save_token_score(conn, "0xT", "0xP", 65.0, 70.0, "watchlist", "[]", "{}", "first", "launch_score_v1", scored_ts=1710000000)
    dbmod.save_candidate(conn, "0xT", "0xP", "watchlist", first_id, event_ts=1710000000)
    second_id = dbmod.save_token_score(conn, "0xT", "0xP", 90.0, 90.0, "candidate", "[]", "{}", "second", "launch_score_v1", scored_ts=1710000100)
    dbmod.save_candidate(conn, "0xT", "0xP", "candidate", second_id, event_ts=1710000100)
    candidate = dbmod.get_candidate(conn, "0xT", "0xP")
    assert candidate["latest_score_id"] == second_id
    assert candidate["observations_count"] == 2
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
