import sqlite3
import time
from typing import List, Optional, Tuple


def _token_scores_has_legacy_unique_constraint(cur: sqlite3.Cursor) -> bool:
    cur.execute("PRAGMA index_list(token_scores)")
    for index in cur.fetchall():
        index_name = index[1]
        is_unique = bool(index[2])
        if not is_unique:
            continue
        cur.execute(f"PRAGMA index_info({index_name})")
        columns = [row[2] for row in cur.fetchall()]
        if columns == ["token_address", "pair_address", "scoring_version"]:
            return True
    return False


def _ensure_token_scores_history_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    if not _token_scores_has_legacy_unique_constraint(cur):
        return

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS token_scores_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT NOT NULL,
            pair_address TEXT,
            score REAL NOT NULL,
            confidence REAL NOT NULL,
            decision TEXT NOT NULL,
            risk_flags TEXT,
            component_scores TEXT,
            reason TEXT,
            scoring_version TEXT NOT NULL,
            scored_block INTEGER,
            scored_ts INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        INSERT INTO token_scores_new(id,token_address,pair_address,score,confidence,decision,risk_flags,component_scores,reason,scoring_version,scored_block,scored_ts)
        SELECT id,token_address,pair_address,score,confidence,decision,risk_flags,component_scores,reason,scoring_version,scored_block,scored_ts
        FROM token_scores
        ORDER BY id
        """
    )
    cur.execute("DROP TABLE token_scores")
    cur.execute("ALTER TABLE token_scores_new RENAME TO token_scores")
    conn.commit()


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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS token_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT NOT NULL,
            pair_address TEXT,
            score REAL NOT NULL,
            confidence REAL NOT NULL,
            decision TEXT NOT NULL,
            risk_flags TEXT,
            component_scores TEXT,
            reason TEXT,
            scoring_version TEXT NOT NULL,
            scored_block INTEGER,
            scored_ts INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates (
            token_address TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            status TEXT NOT NULL,
            latest_score_id INTEGER NOT NULL,
            first_seen_block INTEGER,
            first_seen_ts INTEGER,
            created_ts INTEGER NOT NULL,
            updated_ts INTEGER NOT NULL,
            promoted_block INTEGER,
            promoted_ts INTEGER,
            demoted_block INTEGER,
            demoted_ts INTEGER,
            status_reason TEXT,
            observations_count INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (token_address, pair_address)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pair_liquidity (
            pair_address TEXT PRIMARY KEY,
            token0 TEXT,
            token1 TEXT,
            reserve0 TEXT,
            reserve1 TEXT,
            block_timestamp_last INTEGER,
            pair_total_supply TEXT,
            analysis_block INTEGER,
            analysis_ts INTEGER,
            created_ts INTEGER NOT NULL,
            updated_ts INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            event_type TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT,
            score_id INTEGER,
            status_reason TEXT,
            block_number INTEGER,
            event_ts INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            candidate_id TEXT,
            score_id INTEGER,
            action TEXT NOT NULL,
            quantity REAL NOT NULL,
            entry_reason TEXT,
            created_ts INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS paper_positions (
            token_address TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            status TEXT NOT NULL,
            entry_score_id INTEGER,
            entry_score REAL,
            entry_confidence REAL,
            entry_ts INTEGER,
            exit_ts INTEGER,
            exit_reason TEXT,
            PRIMARY KEY (token_address, pair_address)
        )
        """
    )
    # Ensure legacy DBs get the new column if missing
    try:
        cur.execute("ALTER TABLE token_security ADD COLUMN analysis_block INTEGER")
    except Exception:
        # ignore if column already exists
        pass
    try:
        cur.execute("ALTER TABLE token_security ADD COLUMN analysis_ts INTEGER")
    except Exception:
        # ignore if column already exists
        pass
    conn.commit()

    _ensure_token_scores_history_schema(conn)
    cur = conn.cursor()
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_token_scores_token_pair_version_ts ON token_scores(token_address,pair_address,scoring_version,scored_ts)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_token_scores_pair ON token_scores(pair_address)"
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


def save_pair_liquidity(
    conn,
    pair_address: str,
    token0: str = None,
    token1: str = None,
    reserve0: str = None,
    reserve1: str = None,
    block_timestamp_last: int = None,
    pair_total_supply: str = None,
    analysis_block: int = None,
    analysis_ts: int = None,
):
    cur = conn.cursor()
    now = int(time.time())
    if analysis_ts is None:
        analysis_ts = now
    existing = get_pair_liquidity(conn, pair_address)
    created_ts = existing["created_ts"] if existing else now
    cur.execute(
        """
        INSERT OR REPLACE INTO pair_liquidity(pair_address,token0,token1,reserve0,reserve1,block_timestamp_last,pair_total_supply,analysis_block,analysis_ts,created_ts,updated_ts)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            pair_address,
            token0,
            token1,
            reserve0 if reserve0 is not None else None,
            reserve1 if reserve1 is not None else None,
            block_timestamp_last,
            pair_total_supply if pair_total_supply is not None else None,
            analysis_block,
            analysis_ts,
            created_ts,
            now,
        ),
    )
    conn.commit()


def get_pair_liquidity(conn, pair_address: str):
    cur = conn.cursor()
    cur.execute(
        "SELECT pair_address,token0,token1,reserve0,reserve1,block_timestamp_last,pair_total_supply,analysis_block,analysis_ts,created_ts,updated_ts FROM pair_liquidity WHERE pair_address = ?",
        (pair_address,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "pair_address": row[0],
        "token0": row[1],
        "token1": row[2],
        "reserve0": row[3],
        "reserve1": row[4],
        "block_timestamp_last": row[5],
        "pair_total_supply": row[6],
        "analysis_block": row[7],
        "analysis_ts": row[8],
        "created_ts": row[9],
        "updated_ts": row[10],
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


def save_token_score(
    conn,
    token_address: str,
    pair_address: str,
    score: float,
    confidence: float,
    decision: str,
    risk_flags: str,
    component_scores: str,
    reason: str,
    scoring_version: str,
    scored_block: int = None,
    scored_ts: int = None,
):
    cur = conn.cursor()
    if scored_ts is None:
        scored_ts = int(time.time())
    cur.execute(
        "INSERT INTO token_scores(token_address,pair_address,score,confidence,decision,risk_flags,component_scores,reason,scoring_version,scored_block,scored_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            token_address,
            pair_address,
            score,
            confidence,
            decision,
            risk_flags,
            component_scores,
            reason,
            scoring_version,
            scored_block,
            scored_ts,
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_latest_token_score(conn, token_address: str, pair_address: str = None, scoring_version: str = None):
    cur = conn.cursor()
    query = "SELECT id,token_address,pair_address,score,confidence,decision,risk_flags,component_scores,reason,scoring_version,scored_block,scored_ts FROM token_scores WHERE token_address = ?"
    params = [token_address]
    if pair_address is not None:
        query += " AND pair_address = ?"
        params.append(pair_address)
    if scoring_version is not None:
        query += " AND scoring_version = ?"
        params.append(scoring_version)
    query += " ORDER BY scored_ts DESC, id DESC LIMIT 1"
    cur.execute(query, tuple(params))
    row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "token_address": row[1],
        "pair_address": row[2],
        "score": row[3],
        "confidence": row[4],
        "decision": row[5],
        "risk_flags": row[6],
        "component_scores": row[7],
        "reason": row[8],
        "scoring_version": row[9],
        "scored_block": row[10],
        "scored_ts": row[11],
    }


def get_candidate(conn, token_address: str, pair_address: str):
    cur = conn.cursor()
    cur.execute(
        "SELECT token_address,pair_address,status,latest_score_id,first_seen_block,first_seen_ts,created_ts,updated_ts,promoted_block,promoted_ts,demoted_block,demoted_ts,status_reason,observations_count FROM candidates WHERE token_address = ? AND pair_address = ?",
        (token_address, pair_address),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "token_address": row[0],
        "pair_address": row[1],
        "status": row[2],
        "latest_score_id": row[3],
        "first_seen_block": row[4],
        "first_seen_ts": row[5],
        "created_ts": row[6],
        "updated_ts": row[7],
        "promoted_block": row[8],
        "promoted_ts": row[9],
        "demoted_block": row[10],
        "demoted_ts": row[11],
        "status_reason": row[12],
        "observations_count": row[13],
    }


def save_candidate(
    conn,
    token_address: str,
    pair_address: str,
    status: str,
    latest_score_id: int,
    first_seen_block: int = None,
    first_seen_ts: int = None,
    block_number: int = None,
    status_reason: str = None,
    event_ts: int = None,
):
    cur = conn.cursor()
    now = event_ts if event_ts is not None else int(time.time())
    existing = get_candidate(conn, token_address, pair_address)
    promoted_block = None
    promoted_ts = None
    demoted_block = None
    demoted_ts = None
    if status in ("candidate", "watchlist"):
        promoted_block = block_number
        promoted_ts = now
    if status in ("risky", "reject", "expired"):
        demoted_block = block_number
        demoted_ts = now

    if existing:
        cur.execute(
            """
            UPDATE candidates
            SET status = ?,
                latest_score_id = ?,
                updated_ts = ?,
                promoted_block = COALESCE(promoted_block, ?),
                promoted_ts = COALESCE(promoted_ts, ?),
                demoted_block = ?,
                demoted_ts = ?,
                status_reason = ?,
                observations_count = observations_count + 1
            WHERE token_address = ? AND pair_address = ?
            """,
            (
                status,
                latest_score_id,
                now,
                promoted_block,
                promoted_ts,
                demoted_block if status in ("risky", "reject", "expired") else existing["demoted_block"],
                demoted_ts if status in ("risky", "reject", "expired") else existing["demoted_ts"],
                status_reason,
                token_address,
                pair_address,
            ),
        )
    else:
        cur.execute(
            """
            INSERT INTO candidates(token_address,pair_address,status,latest_score_id,first_seen_block,first_seen_ts,created_ts,updated_ts,promoted_block,promoted_ts,demoted_block,demoted_ts,status_reason,observations_count)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                token_address,
                pair_address,
                status,
                latest_score_id,
                first_seen_block,
                first_seen_ts,
                now,
                now,
                promoted_block,
                promoted_ts,
                demoted_block,
                demoted_ts,
                status_reason,
                1,
            ),
        )
    conn.commit()
    return get_candidate(conn, token_address, pair_address)


def save_candidate_event(
    conn,
    token_address: str,
    pair_address: str,
    event_type: str,
    from_status: str = None,
    to_status: str = None,
    score_id: int = None,
    status_reason: str = None,
    block_number: int = None,
    event_ts: int = None,
):
    cur = conn.cursor()
    if event_ts is None:
        event_ts = int(time.time())
    cur.execute(
        "INSERT INTO candidate_events(token_address,pair_address,event_type,from_status,to_status,score_id,status_reason,block_number,event_ts) VALUES(?,?,?,?,?,?,?,?,?)",
        (
            token_address,
            pair_address,
            event_type,
            from_status,
            to_status,
            score_id,
            status_reason,
            block_number,
            event_ts,
        ),
    )
    conn.commit()
    return cur.lastrowid


def list_active_candidates(conn):
    cur = conn.cursor()
    cur.execute(
        "SELECT token_address,pair_address,status,latest_score_id,first_seen_block,first_seen_ts,created_ts,updated_ts,promoted_block,promoted_ts,demoted_block,demoted_ts,status_reason,observations_count FROM candidates WHERE status IN ('candidate','watchlist','risky') ORDER BY updated_ts DESC"
    )
    rows = cur.fetchall()
    return [
        {
            "token_address": row[0],
            "pair_address": row[1],
            "status": row[2],
            "latest_score_id": row[3],
            "first_seen_block": row[4],
            "first_seen_ts": row[5],
            "created_ts": row[6],
            "updated_ts": row[7],
            "promoted_block": row[8],
            "promoted_ts": row[9],
            "demoted_block": row[10],
            "demoted_ts": row[11],
            "status_reason": row[12],
            "observations_count": row[13],
        }
        for row in rows
    ]


def save_paper_trade(
    conn,
    token_address: str,
    pair_address: str,
    candidate_id: str,
    score_id: int,
    action: str,
    quantity: float,
    entry_reason: str,
    created_ts: int = None,
):
    cur = conn.cursor()
    if created_ts is None:
        created_ts = int(time.time())
    cur.execute(
        "INSERT INTO paper_trades(token_address,pair_address,candidate_id,score_id,action,quantity,entry_reason,created_ts) VALUES(?,?,?,?,?,?,?,?)",
        (
            token_address,
            pair_address,
            candidate_id,
            score_id,
            action,
            quantity,
            entry_reason,
            created_ts,
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_paper_trades(conn, token_address: str = None, pair_address: str = None):
    cur = conn.cursor()
    query = "SELECT id,token_address,pair_address,candidate_id,score_id,action,quantity,entry_reason,created_ts FROM paper_trades"
    params = []
    clauses = []
    if token_address is not None:
        clauses.append("token_address = ?")
        params.append(token_address)
    if pair_address is not None:
        clauses.append("pair_address = ?")
        params.append(pair_address)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id"
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    return [
        {
            "id": row[0],
            "token_address": row[1],
            "pair_address": row[2],
            "candidate_id": row[3],
            "score_id": row[4],
            "action": row[5],
            "quantity": row[6],
            "entry_reason": row[7],
            "created_ts": row[8],
        }
        for row in rows
    ]


def save_paper_position(
    conn,
    token_address: str,
    pair_address: str,
    status: str,
    entry_score_id: int,
    entry_score: float,
    entry_confidence: float,
    entry_ts: int = None,
    exit_ts: int = None,
    exit_reason: str = None,
):
    cur = conn.cursor()
    if entry_ts is None:
        entry_ts = int(time.time())
    cur.execute(
        "INSERT OR REPLACE INTO paper_positions(token_address,pair_address,status,entry_score_id,entry_score,entry_confidence,entry_ts,exit_ts,exit_reason) VALUES(?,?,?,?,?,?,?,?,?)",
        (
            token_address,
            pair_address,
            status,
            entry_score_id,
            entry_score,
            entry_confidence,
            entry_ts,
            exit_ts,
            exit_reason,
        ),
    )
    conn.commit()
    return get_paper_position(conn, token_address, pair_address)


def get_paper_position(conn, token_address: str, pair_address: str):
    cur = conn.cursor()
    cur.execute(
        "SELECT token_address,pair_address,status,entry_score_id,entry_score,entry_confidence,entry_ts,exit_ts,exit_reason FROM paper_positions WHERE token_address = ? AND pair_address = ?",
        (token_address, pair_address),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "token_address": row[0],
        "pair_address": row[1],
        "status": row[2],
        "entry_score_id": row[3],
        "entry_score": row[4],
        "entry_confidence": row[5],
        "entry_ts": row[6],
        "exit_ts": row[7],
        "exit_reason": row[8],
    }


def get_open_paper_position(conn, token_address: str, pair_address: str):
    position = get_paper_position(conn, token_address, pair_address)
    if position and position["status"] == "OPEN":
        return position
    return None


def list_open_paper_positions(conn):
    cur = conn.cursor()
    cur.execute(
        "SELECT token_address,pair_address,status,entry_score_id,entry_score,entry_confidence,entry_ts,exit_ts,exit_reason FROM paper_positions WHERE status = 'OPEN' ORDER BY entry_ts"
    )
    rows = cur.fetchall()
    return [
        {
            "token_address": row[0],
            "pair_address": row[1],
            "status": row[2],
            "entry_score_id": row[3],
            "entry_score": row[4],
            "entry_confidence": row[5],
            "entry_ts": row[6],
            "exit_ts": row[7],
            "exit_reason": row[8],
        }
        for row in rows
    ]


def close_paper_position(conn, token_address: str, pair_address: str, exit_ts: int = None, exit_reason: str = None):
    cur = conn.cursor()
    if exit_ts is None:
        exit_ts = int(time.time())
    cur.execute(
        "UPDATE paper_positions SET status = 'CLOSED', exit_ts = ?, exit_reason = ? WHERE token_address = ? AND pair_address = ? AND status = 'OPEN'",
        (exit_ts, exit_reason, token_address, pair_address),
    )
    conn.commit()
    return get_paper_position(conn, token_address, pair_address)
