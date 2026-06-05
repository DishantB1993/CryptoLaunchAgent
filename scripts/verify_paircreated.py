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

    # search recent window
    window = 200
    start = max(0, latest - window)
    end = latest

    tried = {}
    for chunk in [1, 2, 5, 10, 25, 50]:
        print(f"Trying chunk_size={chunk} for range {start}..{end}")
        try:
            logs = fetch_logs_chunked(manager, factory, start, end, topic0, chunk_size=chunk)
            print(f"chunk_size={chunk} returned {len(logs)} logs")
            if logs:
                for log in logs:
                    decoded = decode_paircreated_log(Web3, log)
                    if decoded and decoded.get("pair"):
                        print("Found PairCreated:")
                        print("pair", decoded.get("pair"))
                        print("token0", decoded.get("token0"))
                        print("token1", decoded.get("token1"))
                        tx = Web3.to_hex(decoded.get("tx_hash")) if decoded.get("tx_hash") else None
                        print("tx", tx)
                        print("block", decoded.get("block_number"))
                        return
        except Exception as e:
            print(f"chunk_size={chunk} exception: {e}")
    print("No PairCreated found in recent window")


if __name__ == "__main__":
    main()
