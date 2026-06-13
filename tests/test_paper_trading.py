import json

from src.db import sqlite_storage as dbmod
from src.paper_trading.simulator import run_paper_trading_cycle


TOKEN = "0xT"
PAIR = "0xP"


def add_signal(conn, status="candidate", score=90.0, confidence=90.0, flags=None, reason="entry"):
    if flags is None:
        flags = ["limited_v1_signal_set", "limited_liquidity_signal_set"]
    score_id = dbmod.save_token_score(
        conn,
        TOKEN,
        PAIR,
        score,
        confidence,
        status,
        json.dumps(flags),
        json.dumps({"ownership": 20}),
        reason,
        "launch_score_v1",
        scored_block=100,
        scored_ts=1710000000,
    )
    dbmod.save_candidate(conn, TOKEN, PAIR, status, score_id, first_seen_block=100, block_number=100, status_reason=reason, event_ts=1710000000)
    return score_id


def latest_trade_actions(conn):
    return [trade["action"] for trade in dbmod.get_paper_trades(conn, TOKEN, PAIR)]


def test_buy_created_for_valid_candidate():
    conn = dbmod.init_db(":memory:")
    score_id = add_signal(conn)

    result = run_paper_trading_cycle(conn, now_ts=1710000100)

    assert len(result["opened"]) == 1
    position = dbmod.get_open_paper_position(conn, TOKEN, PAIR)
    assert position["status"] == "OPEN"
    assert position["entry_score_id"] == score_id
    assert position["entry_score"] == 90.0
    assert latest_trade_actions(conn) == ["BUY"]


def test_no_buy_for_watchlist():
    conn = dbmod.init_db(":memory:")
    add_signal(conn, status="watchlist", score=70.0, confidence=80.0)

    result = run_paper_trading_cycle(conn, now_ts=1710000100)

    assert result["opened"] == []
    assert dbmod.get_paper_trades(conn) == []
    assert dbmod.get_paper_position(conn, TOKEN, PAIR) is None


def test_sell_on_reject():
    conn = dbmod.init_db(":memory:")
    add_signal(conn)
    run_paper_trading_cycle(conn, now_ts=1710000100)
    score_id = dbmod.save_token_score(conn, TOKEN, PAIR, 30.0, 90.0, "reject", json.dumps(["zero_reserves"]), "{}", "Pair has zero reserves.", "launch_score_v1", scored_ts=1710000200)
    dbmod.save_candidate(conn, TOKEN, PAIR, "reject", score_id, status_reason="Pair has zero reserves.", event_ts=1710000200)

    result = run_paper_trading_cycle(conn, now_ts=1710000300)

    assert len(result["closed"]) == 1
    position = dbmod.get_paper_position(conn, TOKEN, PAIR)
    assert position["status"] == "CLOSED"
    assert position["exit_reason"] == "candidate_status_reject"
    assert latest_trade_actions(conn) == ["BUY", "SELL"]


def test_sell_on_risky():
    conn = dbmod.init_db(":memory:")
    add_signal(conn)
    run_paper_trading_cycle(conn, now_ts=1710000100)
    score_id = dbmod.save_token_score(conn, TOKEN, PAIR, 50.0, 80.0, "risky", json.dumps(["missing_liquidity"]), "{}", "Missing liquidity.", "launch_score_v1", scored_ts=1710000200)
    dbmod.save_candidate(conn, TOKEN, PAIR, "risky", score_id, status_reason="Missing liquidity.", event_ts=1710000200)

    result = run_paper_trading_cycle(conn, now_ts=1710000300)

    assert len(result["closed"]) == 1
    assert dbmod.get_paper_position(conn, TOKEN, PAIR)["exit_reason"] == "candidate_status_risky"
    assert latest_trade_actions(conn) == ["BUY", "SELL"]


def test_no_duplicate_buy():
    conn = dbmod.init_db(":memory:")
    add_signal(conn)

    run_paper_trading_cycle(conn, now_ts=1710000100)
    result = run_paper_trading_cycle(conn, now_ts=1710000200)

    assert result["opened"] == []
    assert latest_trade_actions(conn) == ["BUY"]
    assert dbmod.get_open_paper_position(conn, TOKEN, PAIR) is not None


def test_position_lifecycle_open_to_closed():
    conn = dbmod.init_db(":memory:")
    add_signal(conn)
    run_paper_trading_cycle(conn, now_ts=1710000100)
    assert dbmod.get_paper_position(conn, TOKEN, PAIR)["status"] == "OPEN"
    score_id = dbmod.save_token_score(conn, TOKEN, PAIR, 30.0, 90.0, "reject", json.dumps(["zero_reserves"]), "{}", "Pair has zero reserves.", "launch_score_v1", scored_ts=1710000200)
    dbmod.save_candidate(conn, TOKEN, PAIR, "expired", score_id, status_reason="expired", event_ts=1710000200)

    run_paper_trading_cycle(conn, now_ts=1710000300)

    position = dbmod.get_paper_position(conn, TOKEN, PAIR)
    assert position["status"] == "CLOSED"
    assert position["entry_ts"] == 1710000100
    assert position["exit_ts"] == 1710000300
    assert position["exit_reason"] == "candidate_status_expired"


def test_trade_history_preserved():
    conn = dbmod.init_db(":memory:")
    add_signal(conn)
    run_paper_trading_cycle(conn, now_ts=1710000100)
    score_id = dbmod.save_token_score(conn, TOKEN, PAIR, 30.0, 90.0, "reject", json.dumps(["zero_reserves"]), "{}", "Pair has zero reserves.", "launch_score_v1", scored_ts=1710000200)
    dbmod.save_candidate(conn, TOKEN, PAIR, "reject", score_id, status_reason="Pair has zero reserves.", event_ts=1710000200)
    run_paper_trading_cycle(conn, now_ts=1710000300)

    trades = dbmod.get_paper_trades(conn, TOKEN, PAIR)

    assert len(trades) == 2
    assert trades[0]["action"] == "BUY"
    assert trades[1]["action"] == "SELL"
    assert trades[0]["created_ts"] == 1710000100
    assert trades[1]["created_ts"] == 1710000300
