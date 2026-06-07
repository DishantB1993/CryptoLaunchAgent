import os
import sqlite3
import tempfile
from src.db import sqlite_storage as dbmod


def test_db_init_and_meta():
    fd, path = tempfile.mkstemp(prefix="test_db_", suffix=".sqlite3")
    os.close(fd)
    conn = dbmod.init_db(path)
    assert conn is not None
    # last_block initially None
    assert dbmod.get_last_block(conn) is None
    dbmod.set_last_block(conn, 12345)
    assert dbmod.get_last_block(conn) == 12345
    # chain id
    assert dbmod.get_chain_id(conn) is None
    dbmod.set_chain_id(conn, 56)
    assert dbmod.get_chain_id(conn) == 56
    # rpc health rows
    dbmod.init_rpc_health_rows(conn, ["https://rpc1", "https://rpc2"])
    h = dbmod.get_rpc_health(conn, "https://rpc1")
    assert h is not None
    # save pair and dedupe
    dbmod.save_pair(conn, "0xPP", "0xT0", "0xT1", "0xF", "0xTX", 100)
    dbmod.save_pair(conn, "0xPP", "0xT0", "0xT1", "0xF", "0xTX", 100)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM pairs WHERE pair_address = ?", ("0xPP",))
    row = cur.fetchone()
    assert row[0] == 1
    conn.close()
    os.remove(path)


def test_legacy_token_security_migration_adds_timing_columns():
    fd, path = tempfile.mkstemp(prefix="test_db_", suffix=".sqlite3")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE token_security (
            token_address TEXT PRIMARY KEY,
            owner_address TEXT,
            is_ownership_renounced INTEGER,
            total_supply TEXT,
            owner_balance TEXT,
            owner_percent REAL,
            has_mint_function INTEGER
        )
        """
    )
    conn.commit()
    conn.close()

    conn = dbmod.init_db(path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(token_security)")
    columns = {row[1] for row in cur.fetchall()}
    assert "analysis_block" in columns
    assert "analysis_ts" in columns
    conn.close()
    os.remove(path)


def test_save_token_security_persists_analysis_timing():
    fd, path = tempfile.mkstemp(prefix="test_db_", suffix=".sqlite3")
    os.close(fd)
    conn = dbmod.init_db(path)
    dbmod.save_token_security(
        conn,
        "0xT",
        "0xOwner",
        False,
        "1000",
        "100",
        10.0,
        False,
        analysis_block=123456,
        analysis_ts=1710000000,
    )
    security = dbmod.get_token_security(conn, "0xT")
    assert security["analysis_block"] == 123456
    assert security["analysis_ts"] == 1710000000
    conn.close()
    os.remove(path)
