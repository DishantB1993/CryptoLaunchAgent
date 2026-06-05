import sqlite3
import time
from typing import List, Optional, Tuple


def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pairs (
            pair_address TEXT PRIMARY KEY,
            token0 TEXT NOT NULL,
            token1 TEXT NOT NULL,
            factory_address TEXT NOT NULL,
            tx_hash TEXT NOT NULL,
            block_number INTEGER NOT NULL,
            first_seen_ts INTEGER NOT NULL
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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS rpc_health (
            url TEXT PRIMARY KEY,
            success_count INTEGER NOT NULL DEFAULT 0,
            failure_count INTEGER NOT NULL DEFAULT 0,
            last_success_ts INTEGER,
            last_failure_ts INTEGER
        )
        """
    )
    conn.commit()
    return conn


def get_last_block(conn: sqlite3.Connection) -> Optional[int]:
    cur = conn.cursor()
    cur.execute("SELECT v FROM meta WHERE k='last_block'")
    row = cur.fetchone()
    if not row:
        return None
    try:
        return int(row[0])
    except Exception:
        return None


def set_last_block(conn: sqlite3.Connection, block: int):
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('last_block',?)", (str(block),))
    conn.commit()


def get_chain_id(conn: sqlite3.Connection) -> Optional[int]:
    cur = conn.cursor()
    cur.execute("SELECT v FROM meta WHERE k='chain_id'")
    row = cur.fetchone()
    if not row:
        return None
    try:
        return int(row[0])
    except Exception:
        return None


def set_chain_id(conn: sqlite3.Connection, chain_id: int):
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('chain_id',?)", (str(chain_id),))
    conn.commit()


def init_rpc_health_rows(conn: sqlite3.Connection, urls: List[str]):
    cur = conn.cursor()
    for u in urls:
        cur.execute(
            "INSERT OR IGNORE INTO rpc_health(url,success_count,failure_count) VALUES(?,?,?)",
            (u, 0, 0),
        )
    conn.commit()


def record_rpc_success(conn: sqlite3.Connection, url: str):
    cur = conn.cursor()
    ts = int(time.time())
    cur.execute(
        "UPDATE rpc_health SET success_count = success_count + 1, last_success_ts = ? WHERE url = ?",
        (ts, url),
    )
    conn.commit()


def record_rpc_failure(conn: sqlite3.Connection, url: str):
    cur = conn.cursor()
    ts = int(time.time())
    cur.execute(
        "UPDATE rpc_health SET failure_count = failure_count + 1, last_failure_ts = ? WHERE url = ?",
        (ts, url),
    )
    conn.commit()


def save_pair(
    conn: sqlite3.Connection,
    pair_address: str,
    token0: str,
    token1: str,
    factory_address: str,
    tx_hash: str,
    block_number: int,
):
    cur = conn.cursor()
    ts = int(time.time())
    cur.execute(
        "INSERT OR IGNORE INTO pairs(pair_address,token0,token1,factory_address,tx_hash,block_number,first_seen_ts) VALUES(?,?,?,?,?,?,?)",
        (pair_address, token0, token1, factory_address, tx_hash, block_number, ts),
    )
    conn.commit()


def get_rpc_health(conn: sqlite3.Connection, url: str) -> Optional[Tuple[int, int, Optional[int], Optional[int]]]:
    cur = conn.cursor()
    cur.execute(
        "SELECT success_count,failure_count,last_success_ts,last_failure_ts FROM rpc_health WHERE url = ?",
        (url,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return row
