#!/usr/bin/env python3
"""PoC: watch PancakeSwap factory for PairCreated events (polling-friendly).

- Uses free public HTTP RPC endpoints (or BSC_RPC_URL env).
- Polls recent blocks and decodes PairCreated logs.
- Minimal SQLite storage to store discovered pairs and last_processed_block.
- Prints pair, token0, token1, tx hash, block number.

Run:
BSC_RPC_URL=https://bsc.publicnode.com .venv/bin/python scripts/pair_watcher_poc.py
"""
import os
import time
import sqlite3
import logging
from typing import Optional

from web3 import Web3, HTTPProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_FACTORY = os.getenv(
    "PANCAKE_FACTORY_ADDRESS",
    "0xca143ce32fe78f1f7019d7d551a6402fc5350c73",
)

DEFAULT_RPCS = [
    os.getenv("BSC_RPC_URL"),
    "https://bsc.publicnode.com",
    "https://bsc-dataseed.binance.org",
    "https://bscrpc.com",
]
DEFAULT_POLL_SECONDS = int(os.getenv("POLL_INTERVAL", "3"))
DB_PATH = os.getenv("PAIR_WATCHER_DB", "pair_watcher.poc.sqlite3")

# PairCreated(signature): PairCreated(address indexed token0, address indexed token1, address pair, uint256)
EVENT_SIG_TEXT = "PairCreated(address,address,address,uint256)"

MAX_CHUNK = 5000  # keep ranges tiny to be friendly to public RPCs


def pick_rpc(urls):
    for url in urls:
        if not url:
            continue
        try:
            w = Web3(HTTPProvider(url, request_kwargs={"timeout": 10}))
            if w.is_connected():
                logger.info("Using RPC %s", url)
                return w
        except Exception:
            logger.debug("RPC %s unreachable", url)
    raise RuntimeError("No reachable RPC endpoint found; set BSC_RPC_URL to a working public RPC")


def init_db(path):
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pairs (
            pair_address TEXT PRIMARY KEY,
            token0 TEXT,
            token1 TEXT,
            tx_hash TEXT,
            block_number INTEGER,
            first_seen_ts INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            k TEXT PRIMARY KEY,
            v TEXT
        )
        """
    )
    conn.commit()
    return conn


def get_last_processed(conn) -> Optional[int]:
    cur = conn.cursor()
    cur.execute("SELECT v FROM meta WHERE k='last_block'")
    row = cur.fetchone()
    if not row:
        return None
    try:
        return int(row[0])
    except Exception:
        return None


def set_last_processed(conn, block_number: int):
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO meta(k,v) VALUES('last_block',?)",
        (str(block_number),),
    )
    conn.commit()


def save_pair(conn, pair_address, token0, token1, tx_hash, block_number):
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO pairs(pair_address,token0,token1,tx_hash,block_number,first_seen_ts) VALUES(?,?,?,?,?,?)",
        (pair_address, token0, token1, tx_hash, block_number, int(time.time())),
    )
    conn.commit()


def decode_paircreated_log(w3: Web3, log) -> Optional[dict]:
    # Topics: [signature, token0(indexed), token1(indexed)]
    topics = log.get("topics")
    if not topics or len(topics) < 3:
        return None
    sig = topics[0]
    # token addresses are indexed topics (left-padded 32 bytes)
    token0 = Web3.to_checksum_address("0x" + topics[1][-40:])
    token1 = Web3.to_checksum_address("0x" + topics[2][-40:])
    # data contains pair (first 32 bytes) and uint (second 32 bytes)
    data = log.get("data", "0x")
    pair_address = None
    try:
        if data and len(data) >= 66:
            data_bytes = bytes.fromhex(data[2:])
            pair_bytes = data_bytes[0:32]
            pair_address = Web3.to_checksum_address("0x" + pair_bytes[-20:].hex())
    except Exception:
        logger.exception("Failed to decode data bytes")
    return {
        "pair": pair_address,
        "token0": token0,
        "token1": token1,
        "tx_hash": log.get("transactionHash"),
        "block_number": int(log.get("blockNumber")),
    }


def fetch_logs_chunked(w3: Web3, factory_addr: str, from_block: int, to_block: int, topic0: str):
    results = []
    start = from_block
    while start <= to_block:
        end = min(start + MAX_CHUNK - 1, to_block)
        try:
            logs = w3.eth.get_logs({
                "fromBlock": start,
                "toBlock": end,
                "address": Web3.to_checksum_address(factory_addr),
                "topics": [topic0],
            })
            if logs:
                results.extend(logs)
        except Exception as e:
            # Be polite: public RPCs sometimes reject ranges; on error, try per-block fallback
            logger.warning("chunk get_logs failed for %s..%s: %s", start, end, getattr(e, "args", e))
            # try per-block
            for b in range(start, end + 1):
                try:
                    logs_b = w3.eth.get_logs({
                        "fromBlock": b,
                        "toBlock": b,
                        "address": Web3.to_checksum_address(factory_addr),
                        "topics": [topic0],
                    })
                    if logs_b:
                        results.extend(logs_b)
                except Exception:
                    # ignore single-block failures
                    pass
        start = end + 1
    return results


def main():
    w3 = pick_rpc(DEFAULT_RPCS)
    conn = init_db(DB_PATH)
    factory = os.getenv("PANCAKE_FACTORY_ADDRESS", DEFAULT_FACTORY)

    event_topic = Web3.keccak(text=EVENT_SIG_TEXT).hex()
    logger.info("PairCreated topic %s", event_topic)

    last = get_last_processed(conn)
    latest = w3.eth.get_block("latest").number
    if last is None:
        # on first run, start from latest-1 to avoid scanning the whole chain
        last = max(0, latest - 1)
        logger.info("No last_block found; starting at %s", last)
        set_last_processed(conn, last)

    logger.info("Starting watch loop (poll %ss) from block %s", DEFAULT_POLL_SECONDS, last + 1)

    try:
        while True:
            try:
                latest = w3.eth.get_block("latest").number
            except Exception:
                logger.exception("Failed to fetch latest block; retrying")
                time.sleep(DEFAULT_POLL_SECONDS)
                continue

            if last < latest:
                from_b = last + 1
                to_b = latest
                # keep scanning small ranges
                logs = fetch_logs_chunked(w3, factory, from_b, to_b, event_topic)
                if logs:
                    for log in logs:
                        decoded = decode_paircreated_log(w3, log)
                        if not decoded:
                            continue
                        pair = decoded["pair"]
                        token0 = decoded["token0"]
                        token1 = decoded["token1"]
                        tx = Web3.to_hex(decoded["tx_hash"]) if decoded["tx_hash"] else None
                        blk = decoded["block_number"]
                        print(f"PairCreated - pair={pair} token0={token0} token1={token1} tx={tx} block={blk}")
                        save_pair(conn, pair, token0, token1, tx, blk)
                # advance last processed to latest
                last = to_b
                set_last_processed(conn, last)

            time.sleep(DEFAULT_POLL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Stopping watcher")
        conn.close()


if __name__ == "__main__":
    main()
