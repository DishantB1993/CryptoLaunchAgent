import time
import traceback
import logging
import random
from typing import List, Optional, Dict

from web3 import Web3, HTTPProvider
from hexbytes import HexBytes

logger = logging.getLogger(__name__)

from src.db.sqlite_storage import record_rpc_failure, record_rpc_success


class RPCManager:
    def __init__(self, urls: List[str], db_conn, request_timeout: int = 10):
        if not urls:
            raise ValueError("No RPC URLs provided")
        self.urls = urls
        self.db = db_conn
        self.request_timeout = request_timeout
        self.current_idx = 0

    def _w3_for(self, url: str) -> Web3:
        return Web3(HTTPProvider(url, request_kwargs={"timeout": self.request_timeout}))

    def _current_url(self) -> str:
        return self.urls[self.current_idx]

    def rotate(self):
        self.current_idx = (self.current_idx + 1) % len(self.urls)

    def get_chain_id(self) -> int:
        # try until success across urls
        attempts = 0
        for _ in range(len(self.urls)):
            url = self._current_url()
            w3 = self._w3_for(url)
            try:
                cid = w3.eth.chain_id
                record_rpc_success(self.db, url)
                return cid
            except Exception as e:
                record_rpc_failure(self.db, url)
                self.rotate()
                attempts += 1
                time.sleep(0.1)
        raise RuntimeError("All RPC endpoints failed to return chain_id")

    def get_latest_block(self) -> int:
        for _ in range(len(self.urls)):
            url = self._current_url()
            w3 = self._w3_for(url)
            try:
                # use block_number which avoids decoding full block and extraData validation
                blk = w3.eth.block_number
                record_rpc_success(self.db, url)
                return blk
            except Exception:
                record_rpc_failure(self.db, url)
                self.rotate()
                time.sleep(0.1)
        raise RuntimeError("All RPC endpoints failed to return latest block")

    def get_logs(self, filter_params: Dict) -> list:
        # filter_params is a dict suitable for w3.eth.get_logs
        max_attempts_per_url = 3
        # normalize filter and topics robustly (handle HexBytes, bytes, ints, nested lists)
        def _norm_topic_item(item):
            if item is None:
                return None
            if isinstance(item, (list, tuple)):
                return [_norm_topic_item(i) for i in item]
            # HexBytes/bytes/ints -> web3 hex string
            if isinstance(item, (bytes, HexBytes)):
                return Web3.to_hex(item)
            if isinstance(item, int):
                return hex(item)
            # strings: ensure 0x prefix
            if isinstance(item, str):
                return item if item.startswith("0x") else ("0x" + item)
            # fallback: convert to str and prefix if needed
            s = str(item)
            return s if s.startswith("0x") else ("0x" + s)

        # Try each configured URL, with a few retries/backoff per URL before rotating
        for _ in range(len(self.urls)):
            url = self._current_url()
            w3 = self._w3_for(url)
            fp = dict(filter_params)
            topics = fp.get("topics")
            if topics is not None:
                fp["topics"] = _norm_topic_item(topics)

            for attempt in range(max_attempts_per_url):
                try:
                    logger.debug("get_logs attempt url=%s from=%s to=%s topics=%s attempt=%d", url, fp.get('fromBlock'), fp.get('toBlock'), fp.get('topics'), attempt)
                    logs = w3.eth.get_logs(fp)
                    record_rpc_success(self.db, url)
                    return logs
                except Exception as e:
                    tb = traceback.format_exc()
                    # transient retry for RPC/server errors; always log
                    logger.error("get_logs failed url=%s filter=%s attempt=%d exception=%s\n%s", url, filter_params, attempt, e, tb)
                    # if last attempt for this url, record failure and rotate
                    if attempt == max_attempts_per_url - 1:
                        record_rpc_failure(self.db, url)
                        self.rotate()
                        # small pause after rotating
                        time.sleep(0.1)
                    else:
                        # exponential backoff with jitter
                        backoff = 0.5 * (2 ** attempt) + random.uniform(0, 0.1)
                        time.sleep(backoff)
                    # continue to next attempt or url

        raise RuntimeError("All RPC endpoints failed to return logs for filter")
