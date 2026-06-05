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
        # backoff sequence per attempt (seconds)
        backoffs = [1, 2, 4, 8, 16, 30]

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

        # Try each configured URL, with multiple retries/backoff per URL before rotating
        for _ in range(len(self.urls)):
            url = self._current_url()
            w3 = self._w3_for(url)
            fp = dict(filter_params)
            topics = fp.get("topics")
            if topics is not None:
                fp["topics"] = _norm_topic_item(topics)

            for attempt, backoff in enumerate(backoffs):
                try:
                    logger.debug(
                        "eth_getLogs request url=%s fromBlock=%s toBlock=%s topics=%s",
                        url,
                        fp.get("fromBlock"),
                        fp.get("toBlock"),
                        fp.get("topics"),
                    )
                    logs = w3.eth.get_logs(fp)
                    # record success and log number of logs
                    try:
                        record_rpc_success(self.db, url)
                    except Exception:
                        # if DB is not available, continue silently
                        logger.debug("record_rpc_success failed for url=%s", url)
                    logger.debug("eth_getLogs success url=%s returned_count=%d", url, len(logs) if logs is not None else 0)
                    return logs
                except Exception as e:
                    tb = traceback.format_exc()
                    # Log full details at DEBUG and concise at ERROR
                    logger.error(
                        "eth_getLogs error url=%s filter=%s attempt=%d exception=%s",
                        url,
                        filter_params,
                        attempt,
                        e,
                    )
                    logger.debug("eth_getLogs traceback:\n%s", tb)

                    # Inspect error payloads for RPC error codes and network/timeouts
                    code = None
                    try:
                        arg0 = e.args[0] if e.args else None
                        if isinstance(arg0, dict):
                            code = arg0.get("code")
                    except Exception:
                        pass

                    # Handle rate-limit / provider limit: rotate immediately
                    if code == -32005:
                        try:
                            record_rpc_failure(self.db, url)
                        except Exception:
                            logger.debug("record_rpc_failure failed for url=%s", url)
                        logger.warning("RPC %s returned rate-limit (-32005); rotating", url)
                        self.rotate()
                        time.sleep(1)
                        break

                    # Handle parse error (bad params) -32701: likely filter formatting
                    if code == -32701:
                        logger.warning("RPC %s returned parse error (-32701) for filter; rotating", url)
                        try:
                            record_rpc_failure(self.db, url)
                        except Exception:
                            logger.debug("record_rpc_failure failed for url=%s", url)
                        self.rotate()
                        time.sleep(1)
                        break

                    # For connection/timeouts and other transient errors, retry with backoff
                    if attempt == len(backoffs) - 1:
                        # last attempt for this URL: mark failure and rotate
                        try:
                            record_rpc_failure(self.db, url)
                        except Exception:
                            logger.debug("record_rpc_failure failed for url=%s", url)
                        logger.warning("All attempts exhausted for url=%s; rotating to next RPC", url)
                        self.rotate()
                        time.sleep(0.1)
                    else:
                        # sleep for configured backoff (bounded)
                        sleep_for = min(backoff, 30)
                        logger.debug("Retrying eth_getLogs after %.1fs (attempt=%d) for url=%s", sleep_for, attempt, url)
                        time.sleep(sleep_for)
                    # continue to next attempt or url

        raise RuntimeError("All RPC endpoints failed to return logs for filter")

    def get_token_metadata(self, token_address: str) -> Dict:
        """
        Try to call ERC20 view methods name(), symbol(), decimals(), totalSupply().
        Returns a dict with keys name,symbol,decimals,totalSupply; values may be None if call fails.
        """
        minimal_abi = [
            {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"},
            {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
            {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
            {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
        ]

        name = None
        symbol = None
        decimals = None
        total_supply = None

        # Try each RPC URL until we get successful calls; don't block on a single provider
        for _ in range(len(self.urls)):
            url = self._current_url()
            w3 = self._w3_for(url)
            try:
                contract = w3.eth.contract(address=w3.to_checksum_address(token_address), abi=minimal_abi)
                # call each in try/except to avoid single failure blocking others
                try:
                    name = contract.functions.name().call()
                except Exception:
                    name = None
                try:
                    symbol = contract.functions.symbol().call()
                except Exception:
                    symbol = None
                try:
                    decimals = contract.functions.decimals().call()
                except Exception:
                    decimals = None
                try:
                    total_supply = contract.functions.totalSupply().call()
                    # normalize to decimal string
                    total_supply = str(total_supply)
                except Exception:
                    total_supply = None

                try:
                    record_rpc_success(self.db, url)
                except Exception:
                    logger.debug("record_rpc_success failed for url=%s", url)

                return {"name": name, "symbol": symbol, "decimals": decimals, "total_supply": total_supply}
            except Exception as e:
                try:
                    record_rpc_failure(self.db, url)
                except Exception:
                    logger.debug("record_rpc_failure failed for url=%s", url)
                # rotate and try next
                self.rotate()
                time.sleep(0.1)

        # All endpoints failed
        return {"name": None, "symbol": None, "decimals": None, "total_supply": None}

    def get_token_security(self, token_address: str, total_supply: Optional[str] = None) -> Dict:
        """
        Basic security analysis for a token contract:
         - attempt to read owner() or getOwner()
         - check if owner == zero address (renounced)
         - read owner token balance and compute percent of total supply
         - detect mint functions by scanning bytecode for selectors
        Returns dict with keys: owner_address, is_ownership_renounced, total_supply, owner_balance, owner_percent, has_mint_function
        """
        owner = None
        is_renounced = False
        owner_balance = None
        owner_percent = None
        has_mint = False

        addr = Web3.to_checksum_address(token_address)

        # Try each configured provider until success
        for _ in range(len(self.urls)):
            url = self._current_url()
            w3 = self._w3_for(url)
            try:
                # record analysis block and timestamp from chain
                try:
                    analysis_block = w3.eth.block_number
                except Exception:
                    analysis_block = None
                try:
                    if analysis_block is not None:
                        block_obj = w3.eth.get_block(analysis_block)
                        analysis_ts = int(block_obj.timestamp)
                    else:
                        analysis_ts = int(time.time())
                except Exception:
                    analysis_ts = int(time.time())

                # attempt owner() then getOwner()
                owner_abi = [
                    {"constant": True, "inputs": [], "name": "owner", "outputs": [{"name": "", "type": "address"}], "type": "function"},
                    {"constant": True, "inputs": [], "name": "getOwner", "outputs": [{"name": "", "type": "address"}], "type": "function"},
                ]
                contract_owner = w3.eth.contract(address=addr, abi=owner_abi)
                try:
                    owner = contract_owner.functions.owner().call()
                except Exception:
                    try:
                        owner = contract_owner.functions.getOwner().call()
                    except Exception:
                        owner = None

                if owner is not None:
                    owner = Web3.to_checksum_address(owner)
                    # treat both ZERO and DEAD as renounced
                    if owner in (Web3.to_checksum_address("0x0000000000000000000000000000000000000000"), Web3.to_checksum_address("0x000000000000000000000000000000000000dEaD")):
                        is_renounced = True

                # total_supply: use provided or call contract via functions
                tsupply = None
                if total_supply is not None:
                    try:
                        tsupply = int(total_supply)
                    except Exception:
                        tsupply = None
                if tsupply is None:
                    try:
                        erc20 = w3.eth.contract(address=addr, abi=[{"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint256"}], "type": "function"}])
                        ts = erc20.functions.totalSupply().call()
                        tsupply = int(ts)
                    except Exception:
                        tsupply = None

                # owner balance via contract.functions.balanceOf(owner).call()
                if owner and tsupply and tsupply > 0:
                    try:
                        erc20 = w3.eth.contract(address=addr, abi=[{"constant": True, "inputs": [{"name": "_owner","type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"}])
                        ob = erc20.functions.balanceOf(owner).call()
                        owner_balance = str(int(ob))
                        owner_percent = (int(ob) / float(tsupply)) * 100.0
                    except Exception:
                        owner_balance = None
                        owner_percent = None

                # detect mint functions by scanning bytecode selectors (expanded set)
                try:
                    code = w3.eth.get_code(addr)
                    code_hex = Web3.to_hex(code)
                    selectors = []
                    sigs = [
                        "mint(address,uint256)",
                        "mint(uint256)",
                        "_mint(address,uint256)",
                        "mintTo(address,uint256)",
                    ]
                    for s in sigs:
                        sel = Web3.keccak(text=s)[:4]
                        sel_hex = Web3.to_hex(sel)
                        selectors.append(sel_hex.replace("0x", ""))
                    # check if any selector hex appears in code
                    for sel in selectors:
                        if sel in code_hex.replace("0x", ""):
                            has_mint = True
                            break
                except Exception:
                    has_mint = False

                try:
                    record_rpc_success(self.db, url)
                except Exception:
                    logger.debug("record_rpc_success failed for url=%s", url)

                # format total_supply back to string if tsupply known
                total_supply_str = str(tsupply) if tsupply is not None else None

                return {
                    "owner_address": owner,
                    "is_ownership_renounced": is_renounced,
                    "total_supply": total_supply_str,
                    "owner_balance": owner_balance,
                    "owner_percent": owner_percent,
                    "has_mint_function": has_mint,
                    "analysis_block": analysis_block,
                    "analysis_ts": analysis_ts,
                }
            except Exception:
                try:
                    record_rpc_failure(self.db, url)
                except Exception:
                    logger.debug("record_rpc_failure failed for url=%s", url)
                self.rotate()
                time.sleep(0.1)

        return {"owner_address": None, "is_ownership_renounced": False, "total_supply": None, "owner_balance": None, "owner_percent": None, "has_mint_function": False, "analysis_block": None, "analysis_ts": None}
