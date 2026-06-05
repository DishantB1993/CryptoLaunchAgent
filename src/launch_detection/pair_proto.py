"""Minimal PairCreated discovery prototype.

Connects to a BSC RPC and PancakeSwap factory, fetches PairCreated events
for a specified block range, decodes them and prints pair info.

No persistence, no resume logic, no trading.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any

from web3 import Web3

# Ensure project root is on sys.path when running this script directly
import os
import sys
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.blockchain.provider import HTTPProvider, ProviderError

LOGGER = logging.getLogger(__name__)

# Minimal PairCreated event ABI
PAIR_CREATED_EVENT_ABI = {
    "anonymous": False,
    "inputs": [
        {"indexed": True, "internalType": "address", "name": "token0", "type": "address"},
        {"indexed": True, "internalType": "address", "name": "token1", "type": "address"},
        {"indexed": False, "internalType": "address", "name": "pair", "type": "address"},
        {"indexed": False, "internalType": "uint256", "name": "", "type": "uint256"},
    ],
    "name": "PairCreated",
    "type": "event",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PairCreated discovery prototype")
    p.add_argument("--from-block", type=int, help="Start block (inclusive)")
    p.add_argument("--to-block", type=int, help="End block (inclusive)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)

    rpc = os.getenv("BSC_RPC_URL")
    factory = os.getenv("PANCAKE_FACTORY_ADDRESS")
    if not rpc:
        print("ERROR: BSC_RPC_URL not set")
        return 2
    if not factory:
        print("ERROR: PANCAKE_FACTORY_ADDRESS not set")
        return 2

    provider = HTTPProvider(rpc)
    try:
        provider.connect()
    except ProviderError as exc:
        print(f"ERROR: Failed to connect to RPC: {exc}")
        return 2

    w3 = provider.w3
    if not w3:
        print("ERROR: provider has no active Web3 instance")
        return 2

    try:
        latest = w3.eth.block_number
    except Exception as exc:
        print(f"ERROR: Failed to fetch latest block: {exc}")
        return 2

    from_block = args.from_block
    to_block = args.to_block
    if from_block is None or to_block is None:
        # default: scan last 10 blocks (keep range small to avoid provider limits)
        to_block = latest
        from_block = max(0, latest - 10)

    print(f"Scanning PairCreated events from {from_block} to {to_block} against factory {factory}")

    # Use checksum addresses
    try:
        factory_addr = w3.to_checksum_address(factory)
    except Exception:
        factory_addr = factory

    # Prepare contract for decoding
    contract = w3.eth.contract(address=factory_addr, abi=[PAIR_CREATED_EVENT_ABI])

    # Compute event topic (signature) and ensure a single 0x prefix
    event_signature_text = "PairCreated(address,address,address,uint256)"
    raw_topic = Web3.keccak(text=event_signature_text).hex()
    event_topic = raw_topic if raw_topic.startswith("0x") else f"0x{raw_topic}"

    # Fetch logs (attempt range fetch; fall back to per-block fetch on failure)
    logs = []
    try:
        logs = w3.eth.get_logs({
            "fromBlock": from_block,
            "toBlock": to_block,
            "address": factory_addr,
            "topics": [event_topic],
        })
    except Exception as exc:
        print(f"WARN: Bulk get_logs failed: {exc}; falling back to per-block queries")
        for b in range(from_block, to_block + 1):
            try:
                blk_logs = w3.eth.get_logs({
                    "fromBlock": b,
                    "toBlock": b,
                    "address": factory_addr,
                    "topics": [event_topic],
                })
                if blk_logs:
                    logs.extend(blk_logs)
            except Exception as exc_block:
                # If provider returns a rate-limit / "limit exceeded" error, stop further blocks.
                try:
                    err = exc_block.args[0]
                    if isinstance(err, dict) and err.get("code") == -32005:
                        print(f"WARN: provider rate limit at block {b}: {err}; stopping per-block fallback")
                        break
                except Exception:
                    pass
                print(f"WARN: get_logs failed for block {b}: {exc_block}")
                continue

    if not logs:
        print("No PairCreated events found in the given range.")
        provider.disconnect()
        return 0

    for log in logs:
        try:
            ev = contract.events.PairCreated().process_log(log)  # type: ignore[attr-defined]
            args: Any = ev.args
            pair = args.get("pair") or args.get("pair_address")
            token0 = args.get("token0")
            token1 = args.get("token1")
            tx_hash = log.get("transactionHash").hex() if log.get("transactionHash") else None
            blk = log.get("blockNumber")
            print(f"pair={pair} token0={token0} token1={token1} tx={tx_hash} block={blk}")
        except Exception as exc:
            print(f"WARNING: Failed to decode log: {exc}; raw_log={log}")

    provider.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
