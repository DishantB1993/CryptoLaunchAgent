from src.db import sqlite_storage as dbmod
from src.launch_detection import watcher
from src.launch_detection.watcher import decode_paircreated_log
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
