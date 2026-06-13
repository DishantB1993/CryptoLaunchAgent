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


class FakeCall:
    def __init__(self, value):
        self.value = value

    def call(self):
        return self.value


class FakePairFunctions:
    def token0(self):
        return FakeCall("0x" + "11" * 20)

    def token1(self):
        return FakeCall("0x" + "22" * 20)

    def getReserves(self):
        return FakeCall((1000, 2000, 1710000000))

    def totalSupply(self):
        return FakeCall(100)


class FakePairContract:
    functions = FakePairFunctions()


class FakePairW3:
    def __init__(self):
        self.eth = self
        self.block_number = 123456

    def get_block(self, block_number):
        class B:
            timestamp = 1710000010

        return B()

    def contract(self, address, abi):
        return FakePairContract()


def test_get_pair_liquidity_reads_pair_contract():
    fd, path = tempfile.mkstemp(prefix="test_db_", suffix=".sqlite3")
    os.close(fd)
    conn = dbmod.init_db(path)
    dbmod.init_rpc_health_rows(conn, ["rpc://good"])
    mgr = RPCManager(["rpc://good"], conn)
    mgr._w3_for = lambda url: FakePairW3()

    liquidity = mgr.get_pair_liquidity("0x" + "aa" * 20)

    assert liquidity["reserve0"] == "1000"
    assert liquidity["reserve1"] == "2000"
    assert liquidity["block_timestamp_last"] == 1710000000
    assert liquidity["pair_total_supply"] == "100"
    assert liquidity["analysis_block"] == 123456
    assert liquidity["analysis_ts"] == 1710000010
    conn.close()
    os.remove(path)
