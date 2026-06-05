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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tokens (
            token_address TEXT PRIMARY KEY,
            name TEXT,
            symbol TEXT,
            decimals INTEGER,
            total_supply TEXT,
            first_seen_block INTEGER,
            first_seen_ts INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS token_security (
            token_address TEXT PRIMARY KEY,
            owner_address TEXT,
            is_ownership_renounced INTEGER,
            total_supply TEXT,
            owner_balance TEXT,
            owner_percent REAL,
            has_mint_function INTEGER,
            analysis_block INTEGER,
            analysis_ts INTEGER
        )
        """
    )
    # Ensure legacy DBs get the new column if missing
    try:
        cur.execute("ALTER TABLE token_security ADD COLUMN analysis_block INTEGER")
    except Exception:
        # ignore if column already exists
        pass
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


def get_token(conn, token_address: str):
    cur = conn.cursor()
    cur.execute("SELECT token_address,name,symbol,decimals,total_supply,first_seen_block,first_seen_ts FROM tokens WHERE token_address = ?", (token_address,))
    row = cur.fetchone()
    if not row:
        return None
    return {
        "token_address": row[0],
        "name": row[1],
        "symbol": row[2],
        "decimals": row[3],
        "total_supply": row[4],
        "first_seen_block": row[5],
        "first_seen_ts": row[6],
    }


def save_token(conn, token_address: str, name: str, symbol: str, decimals: int, total_supply: str, first_seen_block: int):
    cur = conn.cursor()
    ts = int(time.time())
    cur.execute(
        "INSERT OR IGNORE INTO tokens(token_address,name,symbol,decimals,total_supply,first_seen_block,first_seen_ts) VALUES(?,?,?,?,?,?,?)",
        (token_address, name, symbol, decimals if decimals is not None else None, total_supply if total_supply is not None else None, first_seen_block, ts),
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


def get_token_security(conn, token_address: str):
    cur = conn.cursor()
    cur.execute(
        "SELECT token_address,owner_address,is_ownership_renounced,total_supply,owner_balance,owner_percent,has_mint_function,analysis_block,analysis_ts FROM token_security WHERE token_address = ?",
        (token_address,)
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "token_address": row[0],
        "owner_address": row[1],
        "is_ownership_renounced": bool(row[2]) if row[2] is not None else None,
        "total_supply": row[3],
        "owner_balance": row[4],
        "owner_percent": row[5],
        "has_mint_function": bool(row[6]) if row[6] is not None else None,
        "analysis_block": row[7],
        "analysis_ts": row[8],
    }


def save_token_security(conn, token_address: str, owner_address: str, is_ownership_renounced: bool, total_supply: str, owner_balance: str, owner_percent: float, has_mint_function: bool, analysis_block: int = None, analysis_ts: int = None):
    cur = conn.cursor()
    ts = int(time.time())
    if analysis_ts is None:
        analysis_ts = ts
    # Use INSERT OR REPLACE to upsert analysis results
    cur.execute(
        "INSERT OR REPLACE INTO token_security(token_address,owner_address,is_ownership_renounced,total_supply,owner_balance,owner_percent,has_mint_function,analysis_block,analysis_ts) VALUES(?,?,?,?,?,?,?,?,?)",
        (
            token_address,
            owner_address,
            1 if is_ownership_renounced else 0,
            total_supply if total_supply is not None else None,
            owner_balance if owner_balance is not None else None,
            owner_percent if owner_percent is not None else None,
            1 if has_mint_function else 0,
            analysis_block,
            analysis_ts,
        ),
    )
    conn.commit()
