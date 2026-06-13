import json

from src.candidates.analytics import expire_candidates
from src.candidates.reevaluator import reevaluate_candidates
from src.db import sqlite_storage as dbmod


TOKEN = "0xT"
PAIR = "0xP"


def seed_candidate(conn, status="watchlist", score=70.0, confidence=80.0, flags=None, ts=1710000000):
    if flags is None:
        flags = ["limited_v1_signal_set", "limited_liquidity_signal_set"]
    dbmod.save_token(conn, TOKEN, "Launch Token", "LAUNCH", 18, "1000000", 100)
    dbmod.save_token_security(
        conn,
        TOKEN,
        "0xOwner",
        False,
        "1000000",
        "100000",
        10.0,
        False,
        analysis_block=100,
        analysis_ts=ts,
    )
    dbmod.save_pair_liquidity(conn, PAIR, TOKEN, "0xBase", "1000000", "100", 1710000000, "10000", 100, ts)
    score_id = dbmod.save_token_score(
        conn,
        TOKEN,
        PAIR,
        score,
        confidence,
        status,
        json.dumps(flags),
        json.dumps({"ownership": 8}),
        "seed",
        "launch_score_v1",
        scored_block=100,
        scored_ts=ts,
    )
    dbmod.save_candidate(conn, TOKEN, PAIR, status, score_id, first_seen_block=100, block_number=100, status_reason="seed", event_ts=ts)
    return score_id


class FakeRPCManager:
    def __init__(self, security_results=None, liquidity_results=None):
        self.security_results = list(security_results or [])
        self.liquidity_results = list(liquidity_results or [])
        self.metadata_calls = 0

    def get_token_metadata(self, token_address):
        self.metadata_calls += 1
        raise AssertionError("reevaluation must not refresh token metadata")

    def get_token_security(self, token_address, total_supply=None):
        return self.security_results.pop(0)

    def get_pair_liquidity(self, pair_address):
        return self.liquidity_results.pop(0)


def security(owner_percent=0.1, has_mint=False, block=101):
    return {
        "owner_address": "0xOwner",
        "is_ownership_renounced": True,
        "total_supply": "1000000",
        "owner_balance": "1000",
        "owner_percent": owner_percent,
        "has_mint_function": has_mint,
        "analysis_block": block,
        "analysis_ts": 1710000000 + block,
    }


def liquidity(reserve0="1000000", reserve1="100", block=101):
    return {
        "pair_address": PAIR,
        "token0": TOKEN,
        "token1": "0xBase",
        "reserve0": reserve0,
        "reserve1": reserve1,
        "block_timestamp_last": 1710000000,
        "pair_total_supply": "10000",
        "analysis_block": block,
        "analysis_ts": 1710000000 + block,
    }


def score_count(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM token_scores WHERE token_address = ? AND pair_address = ?", (TOKEN, PAIR))
    return cur.fetchone()[0]


def event_count(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM candidate_events WHERE token_address = ? AND pair_address = ?", (TOKEN, PAIR))
    return cur.fetchone()[0]


def test_reevaluation_creates_new_score_record_and_preserves_history():
    conn = dbmod.init_db(":memory:")
    seed_candidate(conn)
    rpc = FakeRPCManager([security()], [liquidity()])

    result = reevaluate_candidates(conn, rpc)

    assert len(result) == 1
    assert score_count(conn) == 2
    latest = dbmod.get_latest_token_score(conn, TOKEN, PAIR, "launch_score_v1")
    assert latest["id"] == result[0]["score_id"]
    assert rpc.metadata_calls == 0


def test_multiple_reevaluations_grow_score_history():
    conn = dbmod.init_db(":memory:")
    seed_candidate(conn)
    rpc = FakeRPCManager([security(block=101), security(block=102), security(block=103)], [liquidity(block=101), liquidity(block=102), liquidity(block=103)])

    reevaluate_candidates(conn, rpc)
    reevaluate_candidates(conn, rpc)
    reevaluate_candidates(conn, rpc)

    assert score_count(conn) == 4


def test_candidate_promotion_after_improved_score_creates_event():
    conn = dbmod.init_db(":memory:")
    seed_candidate(conn, status="watchlist", score=70.0, confidence=80.0)
    rpc = FakeRPCManager([security(owner_percent=0.1)], [liquidity()])

    reevaluate_candidates(conn, rpc)

    candidate = dbmod.get_candidate(conn, TOKEN, PAIR)
    assert candidate["status"] == "candidate"
    assert event_count(conn) == 1
    cur = conn.cursor()
    cur.execute("SELECT from_status, to_status FROM candidate_events")
    event = cur.fetchone()
    assert event[0] == "watchlist"
    assert event[1] == "candidate"


def test_candidate_demotion_after_worse_score_creates_event():
    conn = dbmod.init_db(":memory:")
    seed_candidate(conn, status="candidate", score=90.0, confidence=90.0)
    rpc = FakeRPCManager([security(has_mint=True)], [liquidity()])

    reevaluate_candidates(conn, rpc)

    candidate = dbmod.get_candidate(conn, TOKEN, PAIR)
    assert candidate["status"] == "reject"
    assert event_count(conn) == 1


def test_liquidity_deterioration_reduces_score_and_rejects_candidate():
    conn = dbmod.init_db(":memory:")
    seed_candidate(conn, status="candidate", score=90.0, confidence=90.0)
    rpc = FakeRPCManager([security()], [liquidity(reserve0="0", reserve1="0")])

    result = reevaluate_candidates(conn, rpc)

    candidate = dbmod.get_candidate(conn, TOKEN, PAIR)
    assert candidate["status"] == "reject"
    assert result[0]["score_result"]["score"] <= 30
    assert "zero_reserves" in result[0]["score_result"]["risk_flags"]
    assert event_count(conn) == 1


def test_no_event_when_status_remains_unchanged():
    conn = dbmod.init_db(":memory:")
    seed_candidate(conn, status="candidate", score=90.0, confidence=90.0)
    rpc = FakeRPCManager([security()], [liquidity()])

    reevaluate_candidates(conn, rpc)

    assert dbmod.get_candidate(conn, TOKEN, PAIR)["status"] == "candidate"
    assert event_count(conn) == 0


def test_expiration_helper_compatibility_after_reevaluation():
    conn = dbmod.init_db(":memory:")
    seed_candidate(conn, status="candidate", score=90.0, confidence=90.0, ts=1000)
    rpc = FakeRPCManager([security(block=101)], [liquidity(block=101)])
    reevaluate_candidates(conn, rpc)

    expired = expire_candidates(conn, now_ts=2000, expire_after_seconds=500, block_number=200)

    assert len(expired) == 1
    assert dbmod.get_candidate(conn, TOKEN, PAIR)["status"] == "expired"
