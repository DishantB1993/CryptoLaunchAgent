from src.launch_detection.watcher import decode_paircreated_log
from web3 import Web3


def make_sample_log(pair, token0, token1, block=100, tx=b"\x11"*32):
    # topics: signature, token0, token1
    sig = Web3.keccak(text="PairCreated(address,address,address,uint256)").hex()
    t0 = "0x" + token0[2:].rjust(64, "0")
    t1 = "0x" + token1[2:].rjust(64, "0")
    # data: pair (32) + uint256 (32)
    pair_data = bytes.fromhex(pair[2:])
    pair_padded = (b"\x00" * 12) + pair_data
    data = "0x" + pair_padded.hex() + ("00" * 32)
    return {"topics": [sig, t0, t1], "data": data, "transactionHash": tx, "blockNumber": block}


def test_decode_valid():
    pair = "0x" + "aa" * 20
    t0 = "0x" + "11" * 20
    t1 = "0x" + "22" * 20
    log = make_sample_log(pair, t0, t1)
    decoded = decode_paircreated_log(Web3, log)
    assert decoded["pair"].lower() == pair.lower()
    assert decoded["token0"].lower() == t0.lower()
    assert decoded["token1"].lower() == t1.lower()
