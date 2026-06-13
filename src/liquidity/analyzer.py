from __future__ import annotations

from typing import Any


def _positive_int(value: Any) -> bool:
    try:
        return int(value) > 0
    except Exception:
        return False


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def analyze_pair_liquidity(liquidity: dict | None) -> dict:
    flags = ["limited_liquidity_signal_set"]
    component_score = 0
    caps: list[int] = []

    if liquidity is None:
        flags.append("missing_liquidity")
        caps.append(70)
        return {"risk_flags": flags, "component_score": component_score, "caps": caps}

    reserve0 = _int_or_none(liquidity.get("reserve0"))
    reserve1 = _int_or_none(liquidity.get("reserve1"))
    total_supply = _int_or_none(liquidity.get("pair_total_supply"))

    if liquidity.get("analysis_block") is None or reserve0 is None or reserve1 is None:
        flags.append("liquidity_unreadable")
        caps.append(70)
        return {"risk_flags": flags, "component_score": component_score, "caps": caps}

    component_score += 4

    if reserve0 == 0 and reserve1 == 0:
        flags.append("zero_reserves")
        caps.append(30)
    elif reserve0 == 0 or reserve1 == 0:
        flags.append("one_sided_liquidity")
        caps.append(40)
    else:
        component_score += 4

    if liquidity.get("pair_total_supply") is None:
        flags.append("missing_pair_total_supply")
        caps.append(70)
    elif not _positive_int(total_supply):
        flags.append("zero_pair_total_supply")
        caps.append(40)
    else:
        component_score += 2

    if liquidity.get("block_timestamp_last") is None:
        flags.append("stale_reserves")

    return {"risk_flags": flags, "component_score": component_score, "caps": caps}
