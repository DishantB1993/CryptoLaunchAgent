import json

from src.db import sqlite_storage as dbmod
from src.launch_detection import watcher
from src.launch_detection.watcher import decode_paircreated_log
from src.scoring.launch_score import SCORING_VERSION
from web3 import Web3


def make_sample_log(pair, token0, token1, block=100, tx=b"\x11"*32):
    # topics: signature, token0, token1
    sig = Web3.keccak(text="PairCreated(address,address,address,uint256)").hex()
    t0 = "0x" + token0[2:].rjust(64, "0")
    t1 = "0x" + token1[2:].rjust(64, "0")
    # data: pair (32) + uint256 (32)
    pair_data = bytes.fromhex(pair[2:])
    pair_padded = (b"\x00" * 12) + pair_data
    data = "0x" + pair_padded.hex() + ("00" * 32)
    return {"topics": [sig, t0, t1], "data": data, "transactionHash": tx, "blockNumber": block}


def test_decode_valid():
    pair = "0x" + "aa" * 20
    t0 = "0x" + "11" * 20
    t1 = "0x" + "22" * 20
    log = make_sample_log(pair, t0, t1)
    decoded = decode_paircreated_log(Web3, log)
    assert decoded["pair"].lower() == pair.lower()
    assert decoded["token0"].lower() == t0.lower()
    assert decoded["token1"].lower() == t1.lower()


def test_watch_loop_persists_security_analysis_timing(monkeypatch):
    token0 = "0x" + "11" * 20
    token1 = "0x" + "22" * 20
    pair = "0x" + "aa" * 20
    log = make_sample_log(pair, token0, token1, block=101)
    conn = dbmod.init_db(":memory:")

    class FakeRPCManager:
        def __init__(self, urls, db_conn):
            self.urls = urls
            self.db_conn = db_conn

        def get_chain_id(self):
            return 56

        def get_latest_block(self):
            return 101

        def get_token_metadata(self, token_address):
            return {
                "name": "Test Token",
                "symbol": "TEST",
                "decimals": 18,
                "total_supply": "1000",
            }

        def get_token_security(self, token_address, total_supply=None):
            return {
                "owner_address": "0x" + "33" * 20,
                "is_ownership_renounced": False,
                "total_supply": total_supply,
                "owner_balance": "100",
                "owner_percent": 10.0,
                "has_mint_function": False,
                "analysis_block": 123456,
                "analysis_ts": 1710000000,
            }

        def get_pair_liquidity(self, pair_address):
            return {
                "pair_address": pair_address,
                "token0": token0,
                "token1": token1,
                "reserve0": "1000000",
                "reserve1": "100",
                "block_timestamp_last": 1710000000,
                "pair_total_supply": "10000",
                "analysis_block": 123456,
                "analysis_ts": 1710000000,
            }

    monkeypatch.setattr(watcher, "RPCManager", FakeRPCManager)
    monkeypatch.setattr(watcher, "fetch_logs_chunked", lambda *args, **kwargs: [log])
    monkeypatch.setattr(watcher.time, "sleep", lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt))

    watcher.run_watch_loop(
        conn,
        ["rpc://fake"],
        "0xca143ce32fe78f1f7019d7d551a6402fc5350c73",
        poll_interval=0,
        block_confirmations=0,
    )

    security = dbmod.get_token_security(conn, Web3.to_checksum_address(token0))
    assert security["analysis_block"] == 123456
    assert security["analysis_ts"] == 1710000000


def test_watch_loop_scores_non_base_token_only(monkeypatch):
    wbnb = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
    new_token = "0x" + "44" * 20
    pair = "0x" + "bb" * 20
    log = make_sample_log(pair, wbnb, new_token, block=101)
    conn = dbmod.init_db(":memory:")

    class FakeRPCManager:
        def __init__(self, urls, db_conn):
            self.urls = urls
            self.db_conn = db_conn

        def get_chain_id(self):
            return 56

        def get_latest_block(self):
            return 101

        def get_token_metadata(self, token_address):
            return {
                "name": "Launch Token",
                "symbol": "LAUNCH",
                "decimals": 18,
                "total_supply": "1000000",
            }

        def get_token_security(self, token_address, total_supply=None):
            return {
                "owner_address": "0x" + "55" * 20,
                "is_ownership_renounced": True,
                "total_supply": total_supply,
                "owner_balance": "1000",
                "owner_percent": 0.1,
                "has_mint_function": False,
                "analysis_block": 123456,
                "analysis_ts": 1710000000,
            }

        def get_pair_liquidity(self, pair_address):
            return {
                "pair_address": pair_address,
                "token0": wbnb,
                "token1": new_token,
                "reserve0": "100",
                "reserve1": "1000000",
                "block_timestamp_last": 1710000000,
                "pair_total_supply": "10000",
                "analysis_block": 123456,
                "analysis_ts": 1710000000,
            }

    monkeypatch.setattr(watcher, "RPCManager", FakeRPCManager)
    monkeypatch.setattr(watcher, "fetch_logs_chunked", lambda *args, **kwargs: [log])
    monkeypatch.setattr(watcher.time, "sleep", lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt))

    watcher.run_watch_loop(
        conn,
        ["rpc://fake"],
        "0xca143ce32fe78f1f7019d7d551a6402fc5350c73",
        poll_interval=0,
        block_confirmations=0,
    )

    new_token_score = dbmod.get_latest_token_score(
        conn,
        Web3.to_checksum_address(new_token),
        Web3.to_checksum_address(pair),
        SCORING_VERSION,
    )
    base_token_score = dbmod.get_latest_token_score(
        conn,
        Web3.to_checksum_address(wbnb),
        Web3.to_checksum_address(pair),
        SCORING_VERSION,
    )

    assert new_token_score is not None
    assert new_token_score["decision"] == "candidate"
    assert new_token_score["confidence"] == 90.0
    assert json.loads(new_token_score["risk_flags"]) == ["limited_v1_signal_set", "limited_liquidity_signal_set"]
    assert json.loads(new_token_score["component_scores"])["mint"] == 15
    assert json.loads(new_token_score["component_scores"])["liquidity"] == 10
    assert base_token_score is None

    liquidity = dbmod.get_pair_liquidity(conn, Web3.to_checksum_address(pair))
    assert liquidity["reserve0"] == "100"
    assert liquidity["reserve1"] == "1000000"

    candidate = dbmod.get_candidate(
        conn,
        Web3.to_checksum_address(new_token),
        Web3.to_checksum_address(pair),
    )
    assert candidate is not None
    assert candidate["status"] == "candidate"
    assert candidate["latest_score_id"] == new_token_score["id"]

    cur = conn.cursor()
    cur.execute("SELECT event_type, to_status FROM candidate_events WHERE token_address = ?", (Web3.to_checksum_address(new_token),))
    event = cur.fetchone()
    assert event[0] == "candidate_created"
    assert event[1] == "candidate"
