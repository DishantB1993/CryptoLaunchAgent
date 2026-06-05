#!/usr/bin/env python3
"""Verify PairCreated events on BSC using RPCs and different chunk sizes."""
import os
import sys
import logging

from web3 import Web3

from src.db import sqlite_storage as dbmod
from src.launch_detection.rpc_manager import RPCManager
from src.launch_detection.watcher import decode_paircreated_log, fetch_logs_chunked, EVENT_SIG_TEXT


logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")


def main():
    rpc = os.getenv("BSC_RPC_URL", "https://bsc.publicnode.com")
    rpc_urls = [rpc]
    db_conn = dbmod.init_db(":memory:")
    manager = RPCManager(rpc_urls, db_conn)
    factory = os.getenv("PANCAKE_FACTORY_ADDRESS", "0xca143ce32fe78f1f7019d7d551a6402fc5350c73")

    topic0 = Web3.to_hex(Web3.keccak(text=EVENT_SIG_TEXT))

    try:
        latest = manager.get_latest_block()
    except Exception as e:
        print("Failed to get latest block:", e)
        sys.exit(2)

    # scan latest-20 .. latest with 1-block chunks
    start = max(0, latest - 20)
    end = latest

    for b in range(start, end + 1):
        try:
            logs = fetch_logs_chunked(manager, factory, b, b, topic0, chunk_size=1)
        except Exception as e:
            print(f"get_logs exception for block {b}: {e}")
            continue

        if not logs:
            continue

        for log in logs:
            decoded = decode_paircreated_log(Web3, log)
            if decoded and decoded.get("pair"):
                pair = decoded.get("pair")
                token0 = decoded.get("token0")
                token1 = decoded.get("token1")
                tx = decoded.get("tx_hash")
                if tx and not isinstance(tx, str):
                    tx = Web3.to_hex(tx)
                block_number = decoded.get("block_number")
                print(f"pair={pair}")
                print(f"token0={token0}")
                print(f"token1={token1}")
                print(f"tx={tx}")
                print(f"block={block_number}")
                return

    print("No PairCreated events found in latest-20..latest")


if __name__ == "__main__":
    main()
