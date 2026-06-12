import os
import time
import logging
from typing import Optional

from web3 import Web3

from src.candidates.tracker import track_candidate_from_score
from src.db import sqlite_storage as dbmod
from src.launch_detection.rpc_manager import RPCManager
from src.scoring.launch_score import SCORING_VERSION, candidate_tokens, score_token

logger = logging.getLogger(__name__)

EVENT_SIG_TEXT = "PairCreated(address,address,address,uint256)"


def decode_paircreated_log(w3: Web3, log) -> Optional[dict]:
    topics = log.get("topics")
    if not topics or len(topics) < 3:
        return None
    try:
        # normalize topics to hex strings (some RPCs return HexBytes)
        norm_topics = []
        for t in topics:
            if not isinstance(t, str):
                t = Web3.to_hex(t)
            if not t.startswith("0x"):
                t = "0x" + t
            norm_topics.append(t)

        token0 = Web3.to_checksum_address("0x" + norm_topics[1][-40:])
        token1 = Web3.to_checksum_address("0x" + norm_topics[2][-40:])

        data = log.get("data", "0x")
        if not isinstance(data, str):
            data = Web3.to_hex(data)
        if not data.startswith("0x"):
            data = "0x" + data
        pair_address = None
        if data and len(data) >= 66:
            data_bytes = bytes.fromhex(data[2:])
            pair_bytes = data_bytes[0:32]
            pair_address = Web3.to_checksum_address("0x" + pair_bytes[-20:].hex())
        # normalize tx hash and block number
        tx = log.get("transactionHash")
        if tx is not None and not isinstance(tx, str):
            tx = Web3.to_hex(tx)
        blk = log.get("blockNumber")
        if isinstance(blk, str):
            if blk.startswith("0x"):
                blk = int(blk, 16)
            else:
                blk = int(blk)
        elif blk is None:
            blk = None

        return {
            "pair": pair_address,
            "token0": token0,
            "token1": token1,
            "tx_hash": tx,
            "block_number": blk,
        }
    except Exception:
        logger.exception("Failed decoding log")
        return None


def fetch_logs_chunked(manager: RPCManager, factory_addr: str, start: int, end: int, topic0: str, chunk_size: int = 50):
    results = []
    cur = start
    while cur <= end:
        to_b = min(cur + chunk_size - 1, end)
        f = {
            "fromBlock": cur,
            "toBlock": to_b,
            "address": Web3.to_checksum_address(factory_addr),
            "topics": [topic0],
        }
        try:
            logs = manager.get_logs(f)
            if logs:
                results.extend(logs)
        except Exception as e:
            logger.warning("chunk get_logs failed for %s..%s: %s", cur, to_b, e)
            # fallback per-block
            for b in range(cur, to_b + 1):
                f2 = {"fromBlock": b, "toBlock": b, "address": Web3.to_checksum_address(factory_addr), "topics": [topic0]}
                try:
                    logs_b = manager.get_logs(f2)
                    if logs_b:
                        results.extend(logs_b)
                except Exception:
                    # ignore single-block failures
                    pass
        cur = to_b + 1
    return results


def run_watch_loop(db_conn, rpc_urls, factory_addr, poll_interval: int = 3, chunk_size: int = 50, block_confirmations: int = 3):
    manager = RPCManager(rpc_urls, db_conn)
    # chain validation
    rpc_chain = manager.get_chain_id()
    if rpc_chain != 56:
        raise RuntimeError(f"RPC chain_id {rpc_chain} != 56 (BSC mainnet required)")
    db_chain = dbmod.get_chain_id(db_conn)
    if db_chain is None:
        dbmod.set_chain_id(db_conn, rpc_chain)
    elif db_chain != rpc_chain:
        raise RuntimeError(f"DB chain_id {db_chain} does not match RPC chain_id {rpc_chain}")

    topic0 = Web3.to_hex(Web3.keccak(text=EVENT_SIG_TEXT))

    last = dbmod.get_last_block(db_conn)
    latest = manager.get_latest_block()
    if last is None:
        # start from latest-1 to avoid scanning history
        last = max(0, latest - 1)
        dbmod.set_last_block(db_conn, last)
    logger.info("Starting watch from block %s", last + 1)

    try:
        while True:
            latest = manager.get_latest_block()
            safe_block = latest - block_confirmations
            if safe_block < 0:
                time.sleep(poll_interval)
                continue
            if last < safe_block:
                from_b = last + 1
                to_b = safe_block
                logs = fetch_logs_chunked(manager, factory_addr, from_b, to_b, topic0, chunk_size=chunk_size)
                if logs:
                    for log in logs:
                        decoded = decode_paircreated_log(Web3, log)
                        if not decoded:
                            continue
                        pair = decoded["pair"]
                        token0 = decoded["token0"]
                        token1 = decoded["token1"]
                        tx = decoded["tx_hash"]
                        if tx is not None and not isinstance(tx, str):
                            tx = Web3.to_hex(tx)
                        blk = decoded["block_number"]
                        print(f"PairCreated - pair={pair} token0={token0} token1={token1} factory={factory_addr} tx={tx} block={blk}")

                        # Save token metadata if not already present (simple caching)
                        try:
                            existing0 = dbmod.get_token(db_conn, Web3.to_checksum_address(token0))
                        except Exception:
                            existing0 = None
                        if not existing0:
                            try:
                                meta0 = manager.get_token_metadata(token0)
                            except Exception:
                                meta0 = {"name": None, "symbol": None, "decimals": None, "total_supply": None}
                            dbmod.save_token(db_conn, Web3.to_checksum_address(token0), meta0.get("name"), meta0.get("symbol"), meta0.get("decimals"), meta0.get("total_supply"), blk)
                            # token security analysis (MVP) - only if not already analyzed
                            try:
                                sec0 = dbmod.get_token_security(db_conn, Web3.to_checksum_address(token0))
                            except Exception:
                                sec0 = None
                            if not sec0:
                                try:
                                    analysis0 = manager.get_token_security(token0, meta0.get("total_supply"))
                                except Exception:
                                    analysis0 = {"owner_address": None, "is_ownership_renounced": False, "total_supply": meta0.get("total_supply"), "owner_balance": None, "owner_percent": None, "has_mint_function": False}
                                dbmod.save_token_security(db_conn, Web3.to_checksum_address(token0), analysis0.get("owner_address"), analysis0.get("is_ownership_renounced"), analysis0.get("total_supply"), analysis0.get("owner_balance"), analysis0.get("owner_percent"), analysis0.get("has_mint_function"), analysis0.get("analysis_block"), analysis0.get("analysis_ts"))

                        try:
                            existing1 = dbmod.get_token(db_conn, Web3.to_checksum_address(token1))
                        except Exception:
                            existing1 = None
                        if not existing1:
                            try:
                                meta1 = manager.get_token_metadata(token1)
                            except Exception:
                                meta1 = {"name": None, "symbol": None, "decimals": None, "total_supply": None}
                            dbmod.save_token(db_conn, Web3.to_checksum_address(token1), meta1.get("name"), meta1.get("symbol"), meta1.get("decimals"), meta1.get("total_supply"), blk)
                            try:
                                sec1 = dbmod.get_token_security(db_conn, Web3.to_checksum_address(token1))
                            except Exception:
                                sec1 = None
                            if not sec1:
                                try:
                                    analysis1 = manager.get_token_security(token1, meta1.get("total_supply"))
                                except Exception:
                                    analysis1 = {"owner_address": None, "is_ownership_renounced": False, "total_supply": meta1.get("total_supply"), "owner_balance": None, "owner_percent": None, "has_mint_function": False}
                                dbmod.save_token_security(db_conn, Web3.to_checksum_address(token1), analysis1.get("owner_address"), analysis1.get("is_ownership_renounced"), analysis1.get("total_supply"), analysis1.get("owner_balance"), analysis1.get("owner_percent"), analysis1.get("has_mint_function"), analysis1.get("analysis_block"), analysis1.get("analysis_ts"))

                        # Save pair record
                        dbmod.save_pair(db_conn, pair, token0, token1, factory_addr, tx, blk)

                        for candidate in candidate_tokens(token0, token1):
                            candidate_addr = Web3.to_checksum_address(candidate)
                            token_data = dbmod.get_token(db_conn, candidate_addr)
                            security_data = dbmod.get_token_security(db_conn, candidate_addr)
                            score_result = score_token(token_data, security_data, pair_address=pair)
                            score_id = dbmod.save_token_score(
                                db_conn,
                                candidate_addr,
                                pair,
                                score_result["score"],
                                score_result["confidence"],
                                score_result["decision"],
                                score_result["risk_flags_json"],
                                score_result["component_scores_json"],
                                score_result["reason"],
                                SCORING_VERSION,
                                scored_block=security_data.get("analysis_block") if security_data else blk,
                            )
                            track_candidate_from_score(
                                db_conn,
                                candidate_addr,
                                pair,
                                score_id,
                                score_result,
                                block_number=blk,
                            )
                # advance last to safe_block
                dbmod.set_last_block(db_conn, safe_block)
                last = safe_block
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("Watcher interrupted; exiting")
