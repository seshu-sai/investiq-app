"""Shared data boundaries and a small, bounded provider cache."""

from collections import OrderedDict
from copy import deepcopy
from functools import wraps
import math
import re
from threading import RLock
from time import monotonic
from urllib.parse import urlsplit


def finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_symbol(market: str, symbol: str) -> str:
    if market not in ("US", "CA", "IN"):
        raise ValueError("Unsupported market")
    ticker = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,31}", ticker):
        raise ValueError("Invalid ticker symbol")
    suffixes = {"CA": (".TO", ".V"), "IN": (".NS", ".BO")}
    for other_market, endings in suffixes.items():
        if ticker.endswith(endings) and market != other_market:
            raise ValueError("Ticker suffix does not match the selected market")
    if market in suffixes and not ticker.endswith(suffixes[market]):
        ticker += suffixes[market][0]
    if len(ticker) > 32:
        raise ValueError("Ticker including exchange suffix must be at most 32 characters")
    return ticker


def safe_url(value):
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme in ("https", "http") and parts.hostname and not parts.username and not parts.password:
            return value
    except ValueError:
        pass
    return None


def ttl_cache(seconds: int, maxsize: int = 256):
    """Cache successful results only; copies prevent per-request mutations."""
    def decorate(function):
        cache = OrderedDict()
        lock = RLock()

        @wraps(function)
        def wrapped(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            with lock:
                cached = cache.get(key)
                if cached and monotonic() - cached[0] < seconds:
                    cache.move_to_end(key)
                    return deepcopy(cached[1])
            result = function(*args, **kwargs)
            with lock:
                cache[key] = (monotonic(), deepcopy(result))
                cache.move_to_end(key)
                while len(cache) > maxsize:
                    cache.popitem(last=False)
            return result

        def clear():
            with lock:
                cache.clear()
        wrapped.cache_clear = clear
        return wrapped
    return decorate
