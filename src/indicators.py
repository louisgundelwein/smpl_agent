"""Technical indicators for candle data. Pure Python, no external dependencies."""

import math
from typing import Any


def _closes(candles: list[dict]) -> list[float]:
    """Extract close prices as floats from candle dicts."""
    return [float(c["c"]) for c in candles]


def _highs(candles: list[dict]) -> list[float]:
    return [float(c["h"]) for c in candles]


def _lows(candles: list[dict]) -> list[float]:
    return [float(c["l"]) for c in candles]


def _volumes(candles: list[dict]) -> list[float]:
    return [float(c["v"]) for c in candles]


# ------------------------------------------------------------------
# Trend Indicators
# ------------------------------------------------------------------


def sma(candles: list[dict], period: int = 20) -> list[float | None]:
    """Simple Moving Average over close prices."""
    closes = _closes(candles)
    result: list[float | None] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        result[i] = sum(closes[i - period + 1 : i + 1]) / period
    return result


def ema(candles: list[dict], period: int = 20) -> list[float | None]:
    """Exponential Moving Average over close prices."""
    closes = _closes(candles)
    result: list[float | None] = [None] * len(closes)
    if len(closes) < period:
        return result
    # Seed with SMA
    seed = sum(closes[:period]) / period
    result[period - 1] = seed
    multiplier = 2.0 / (period + 1)
    prev = seed
    for i in range(period, len(closes)):
        val = (closes[i] - prev) * multiplier + prev
        result[i] = val
        prev = val
    return result


def macd(
    candles: list[dict],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> dict[str, list[float | None]]:
    """MACD: line, signal, histogram."""
    fast_ema = ema(candles, fast)
    slow_ema = ema(candles, slow)
    n = len(candles)

    macd_line: list[float | None] = [None] * n
    for i in range(n):
        if fast_ema[i] is not None and slow_ema[i] is not None:
            macd_line[i] = fast_ema[i] - slow_ema[i]

    # Signal line: EMA of MACD line values
    macd_values = [v for v in macd_line if v is not None]
    signal_line: list[float | None] = [None] * n
    histogram: list[float | None] = [None] * n

    if len(macd_values) >= signal_period:
        seed = sum(macd_values[:signal_period]) / signal_period
        sig_vals: list[float | None] = [None] * (signal_period - 1) + [seed]
        mult = 2.0 / (signal_period + 1)
        prev = seed
        for j in range(signal_period, len(macd_values)):
            val = (macd_values[j] - prev) * mult + prev
            sig_vals.append(val)
            prev = val

        # Map back to original indices
        sig_idx = 0
        for i in range(n):
            if macd_line[i] is not None:
                if sig_idx < len(sig_vals):
                    signal_line[i] = sig_vals[sig_idx]
                    if sig_vals[sig_idx] is not None:
                        histogram[i] = macd_line[i] - sig_vals[sig_idx]
                sig_idx += 1

    return {"macd_line": macd_line, "signal": signal_line, "histogram": histogram}


# ------------------------------------------------------------------
# Momentum Indicators
# ------------------------------------------------------------------


def rsi(candles: list[dict], period: int = 14) -> list[float | None]:
    """Relative Strength Index."""
    closes = _closes(candles)
    result: list[float | None] = [None] * len(closes)
    if len(closes) < period + 1:
        return result

    gains = []
    losses = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    # First average
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - (100.0 / (1.0 + rs))

    # Smoothed (Wilder's method)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i + 1] = 100.0 - (100.0 / (1.0 + rs))

    return result


def stochastic(
    candles: list[dict],
    k_period: int = 14,
    d_period: int = 3,
) -> dict[str, list[float | None]]:
    """Stochastic Oscillator (%K and %D)."""
    highs = _highs(candles)
    lows = _lows(candles)
    closes = _closes(candles)
    n = len(candles)

    k_values: list[float | None] = [None] * n
    for i in range(k_period - 1, n):
        window_high = max(highs[i - k_period + 1 : i + 1])
        window_low = min(lows[i - k_period + 1 : i + 1])
        if window_high == window_low:
            k_values[i] = 50.0
        else:
            k_values[i] = ((closes[i] - window_low) / (window_high - window_low)) * 100.0

    # %D is SMA of %K
    d_values: list[float | None] = [None] * n
    valid_k = [(i, v) for i, v in enumerate(k_values) if v is not None]
    for j in range(d_period - 1, len(valid_k)):
        idx = valid_k[j][0]
        d_values[idx] = sum(valid_k[j - d_period + 1 + x][1] for x in range(d_period)) / d_period

    return {"k": k_values, "d": d_values}


# ------------------------------------------------------------------
# Volatility Indicators
# ------------------------------------------------------------------


def bollinger_bands(
    candles: list[dict],
    period: int = 20,
    std_dev: float = 2.0,
) -> dict[str, list[float | None]]:
    """Bollinger Bands: upper, middle (SMA), lower."""
    closes = _closes(candles)
    n = len(closes)
    middle: list[float | None] = [None] * n
    upper: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n

    for i in range(period - 1, n):
        window = closes[i - period + 1 : i + 1]
        mean = sum(window) / period
        variance = sum((x - mean) ** 2 for x in window) / period
        std = math.sqrt(variance)
        middle[i] = mean
        upper[i] = mean + std_dev * std
        lower[i] = mean - std_dev * std

    return {"upper": upper, "middle": middle, "lower": lower}


def atr(candles: list[dict], period: int = 14) -> list[float | None]:
    """Average True Range."""
    highs = _highs(candles)
    lows = _lows(candles)
    closes = _closes(candles)
    n = len(candles)

    tr_values: list[float] = [highs[0] - lows[0]]
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr_values.append(tr)

    result: list[float | None] = [None] * n
    if n < period:
        return result
    result[period - 1] = sum(tr_values[:period]) / period
    for i in range(period, n):
        result[i] = (result[i - 1] * (period - 1) + tr_values[i]) / period

    return result


# ------------------------------------------------------------------
# Volume Indicators
# ------------------------------------------------------------------


def vwap(candles: list[dict]) -> list[float | None]:
    """Volume Weighted Average Price (running across all candles)."""
    n = len(candles)
    result: list[float | None] = [None] * n
    cum_volume = 0.0
    cum_tp_vol = 0.0

    for i in range(n):
        typical_price = (float(candles[i]["h"]) + float(candles[i]["l"]) + float(candles[i]["c"])) / 3.0
        vol = float(candles[i]["v"])
        cum_volume += vol
        cum_tp_vol += typical_price * vol
        if cum_volume > 0:
            result[i] = cum_tp_vol / cum_volume

    return result


def obv(candles: list[dict]) -> list[float | None]:
    """On Balance Volume."""
    closes = _closes(candles)
    volumes = _volumes(candles)
    n = len(candles)
    if n == 0:
        return []
    result: list[float | None] = [volumes[0]]

    for i in range(1, n):
        if closes[i] > closes[i - 1]:
            result.append(result[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            result.append(result[-1] - volumes[i])
        else:
            result.append(result[-1])

    return result


# ------------------------------------------------------------------
# Convenience
# ------------------------------------------------------------------

_INDICATOR_FUNCS: dict[str, Any] = {
    "sma": sma,
    "ema": ema,
    "macd": macd,
    "rsi": rsi,
    "stochastic": stochastic,
    "bollinger_bands": bollinger_bands,
    "atr": atr,
    "vwap": vwap,
    "obv": obv,
}


def compute_indicators(
    candles: list[dict],
    indicators: list[dict[str, Any]],
    history_length: int = 10,
) -> dict[str, Any]:
    """Compute multiple indicators and return latest + recent history.

    Args:
        candles: List of candle dicts (OHLCV format).
        indicators: List of indicator configs, each like:
            {"name": "rsi", "period": 14}
            {"name": "macd", "fast": 12, "slow": 26, "signal_period": 9}
        history_length: Number of recent values to include per indicator.

    Returns:
        Dict keyed by indicator label with latest value and history.
    """
    results: dict[str, Any] = {}

    for cfg in indicators:
        name = cfg.get("name")
        if not name:
            continue
        func = _INDICATOR_FUNCS.get(name)
        if func is None:
            results[name] = {"error": f"Unknown indicator: {name}"}
            continue

        # Extract params (everything except "name")
        params = {k: v for k, v in cfg.items() if k != "name"}

        try:
            raw = func(candles, **params)
        except Exception as exc:
            results[name] = {"error": str(exc)}
            continue

        # Build label from name + param values
        label_parts = [name] + [str(v) for v in params.values()]
        label = "_".join(label_parts)

        if isinstance(raw, dict):
            # Multi-output indicator (MACD, Bollinger, Stochastic)
            sub_results = {}
            for sub_key, sub_values in raw.items():
                valid = [(i, v) for i, v in enumerate(sub_values) if v is not None]
                if valid:
                    latest = round(valid[-1][1], 6)
                    history = [round(v, 6) for _, v in valid[-history_length:]]
                else:
                    latest = None
                    history = []
                sub_results[sub_key] = {"latest": latest, "history": history}
            results[label] = sub_results
        else:
            # Single-output indicator
            valid = [(i, v) for i, v in enumerate(raw) if v is not None]
            if valid:
                latest = round(valid[-1][1], 6)
                history = [round(v, 6) for _, v in valid[-history_length:]]
            else:
                latest = None
                history = []
            results[label] = {"latest": latest, "history": history}

    return results
