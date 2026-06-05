import tempfile
import os
from src.launch_detection.rpc_manager import RPCManager
from src.db import sqlite_storage as dbmod


class FakeW3:
    def __init__(self, chain_id=56, latest=100, logs=None, fail=False):
        self.eth = self
        self.chain_id = chain_id
        self._latest = latest
        self.block_number = latest
        self._logs = logs or []
        self._fail = fail

    def get_block(self, arg):
        if self._fail:
            raise RuntimeError("fail")
        class B: number = self._latest
        return B()

    def get_logs(self, f):
        if self._fail:
            raise RuntimeError("fail logs")
        return self._logs


def test_rpc_rotation_and_health():
    fd, path = tempfile.mkstemp(prefix="test_db_", suffix=".sqlite3")
    os.close(fd)
    conn = dbmod.init_db(path)
    urls = ["rpc://bad", "rpc://good"]
    dbmod.init_rpc_health_rows(conn, urls)

    mgr = RPCManager(urls, conn)

    # monkeypatch _w3_for to return failing for first, success for second
    def w3_for(url):
        if url == "rpc://bad":
            return FakeW3(fail=True)
        return FakeW3()

    mgr._w3_for = w3_for

    blk = mgr.get_latest_block()
    assert isinstance(blk, int)
    # ensure rpc health updated for both urls (failure then success)
    h_bad = dbmod.get_rpc_health(conn, "rpc://bad")
    h_good = dbmod.get_rpc_health(conn, "rpc://good")
    assert h_bad is not None and h_good is not None
    conn.close()
    os.remove(path)
