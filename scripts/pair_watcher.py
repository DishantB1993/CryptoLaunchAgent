#!/usr/bin/env python3
"""CLI to run the PairCreated watcher"""
import os
import sys
import logging

from src.db import sqlite_storage as dbmod
from src.launch_detection.watcher import run_watch_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def parse_env_list(name: str):
    v = os.getenv(name)
    if not v:
        return []
    return [x.strip() for x in v.split(",") if x.strip()]


def main():
    rpc_urls = parse_env_list("BSC_RPC_URLS") or [os.getenv("BSC_RPC_URL")]
    rpc_urls = [u for u in rpc_urls if u]
    if not rpc_urls:
        print("Please set BSC_RPC_URLS or BSC_RPC_URL environment variable")
        sys.exit(2)

    db_path = os.getenv("PAIR_DB", "pair_watcher.sqlite3")
    factory = os.getenv("PANCAKE_FACTORY_ADDRESS", "0xca143ce32fe78f1f7019d7d551a6402fc5350c73")
    poll_interval = int(os.getenv("POLL_INTERVAL", "3"))
    chunk_size = int(os.getenv("CHUNK_SIZE", "50"))
    block_confirmations = int(os.getenv("BLOCK_CONFIRMATIONS", "3"))

    conn = dbmod.init_db(db_path)
    dbmod.init_rpc_health_rows(conn, rpc_urls)

    try:
        run_watch_loop(conn, rpc_urls, factory, poll_interval=poll_interval, chunk_size=chunk_size, block_confirmations=block_confirmations)
    except Exception as e:
        logging.exception("Watcher failed: %s", e)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
