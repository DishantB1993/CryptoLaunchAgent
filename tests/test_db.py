import os
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
