"""Tests for src.indicators — Technical indicators (pure Python, no mocks needed)."""

import pytest

from src.indicators import (
    atr,
    bollinger_bands,
    compute_indicators,
    ema,
    macd,
    obv,
    rsi,
    sma,
    stochastic,
    vwap,
)


def _make_candles(
    closes: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[float] | None = None,
) -> list[dict]:
    """Build minimal candle dicts from price lists."""
    n = len(closes)
    if highs is None:
        highs = [c + 1 for c in closes]
    if lows is None:
        lows = [c - 1 for c in closes]
    if volumes is None:
        volumes = [100.0] * n
    return [
        {
            "t": i * 3600000,
            "T": (i + 1) * 3600000,
            "o": str(closes[i]),
            "h": str(highs[i]),
            "l": str(lows[i]),
            "c": str(closes[i]),
            "v": str(volumes[i]),
            "i": "1h",
            "s": "ETH",
            "n": 10,
        }
        for i in range(n)
    ]


# ------------------------------------------------------------------
# SMA
# ------------------------------------------------------------------


class TestSMA:
    def test_basic(self):
        candles = _make_candles([10, 20, 30, 40, 50])
        result = sma(candles, period=3)
        assert result[0] is None
        assert result[1] is None
        assert result[2] == pytest.approx(20.0)
        assert result[3] == pytest.approx(30.0)
        assert result[4] == pytest.approx(40.0)

    def test_insufficient_data(self):
        candles = _make_candles([10, 20])
        result = sma(candles, period=5)
        assert all(v is None for v in result)

    def test_constant_values(self):
        candles = _make_candles([50.0] * 10)
        result = sma(candles, period=5)
        for v in result[4:]:
            assert v == pytest.approx(50.0)


# ------------------------------------------------------------------
# EMA
# ------------------------------------------------------------------


class TestEMA:
    def test_first_value_is_sma(self):
        candles = _make_candles([10, 20, 30])
        result = ema(candles, period=3)
        assert result[2] == pytest.approx(20.0)

    def test_converges_on_constant(self):
        candles = _make_candles([100.0] * 20)
        result = ema(candles, period=10)
        assert result[-1] == pytest.approx(100.0)

    def test_insufficient_data(self):
        candles = _make_candles([10, 20])
        result = ema(candles, period=5)
        assert all(v is None for v in result)

    def test_responds_to_trend(self):
        candles = _make_candles(list(range(1, 30)))
        result = ema(candles, period=5)
        # EMA should be increasing for uptrend
        valid = [v for v in result if v is not None]
        for i in range(1, len(valid)):
            assert valid[i] > valid[i - 1]


# ------------------------------------------------------------------
# MACD
# ------------------------------------------------------------------


class TestMACD:
    def test_returns_three_series(self):
        candles = _make_candles(list(range(1, 50)))
        result = macd(candles)
        assert "macd_line" in result
        assert "signal" in result
        assert "histogram" in result
        assert len(result["macd_line"]) == 49

    def test_insufficient_data(self):
        candles = _make_candles([10, 20, 30])
        result = macd(candles)
        assert all(v is None for v in result["macd_line"])

    def test_histogram_is_line_minus_signal(self):
        candles = _make_candles(list(range(1, 60)))
        result = macd(candles)
        for i in range(len(candles)):
            if result["histogram"][i] is not None:
                expected = result["macd_line"][i] - result["signal"][i]
                assert result["histogram"][i] == pytest.approx(expected, abs=1e-6)


# ------------------------------------------------------------------
# RSI
# ------------------------------------------------------------------


class TestRSI:
    def test_all_gains(self):
        candles = _make_candles(list(range(1, 20)))
        result = rsi(candles, period=14)
        assert result[-1] == pytest.approx(100.0)

    def test_all_losses(self):
        candles = _make_candles(list(range(20, 1, -1)))
        result = rsi(candles, period=14)
        assert result[-1] == pytest.approx(0.0)

    def test_range_0_to_100(self):
        prices = [44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 44.02,
                  44.17, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84]
        candles = _make_candles(prices)
        result = rsi(candles, period=14)
        valid = [v for v in result if v is not None]
        for v in valid:
            assert 0 <= v <= 100

    def test_insufficient_data(self):
        candles = _make_candles([10, 20, 30])
        result = rsi(candles, period=14)
        assert all(v is None for v in result)


# ------------------------------------------------------------------
# Stochastic
# ------------------------------------------------------------------


class TestStochastic:
    def test_returns_k_and_d(self):
        candles = _make_candles(list(range(1, 30)))
        result = stochastic(candles, k_period=14, d_period=3)
        assert "k" in result
        assert "d" in result
        assert len(result["k"]) == 29

    def test_k_range(self):
        prices = [10, 15, 12, 18, 20, 8, 14, 16, 19, 11, 13, 17, 9, 15, 12, 18]
        candles = _make_candles(prices)
        result = stochastic(candles, k_period=14, d_period=3)
        valid_k = [v for v in result["k"] if v is not None]
        for v in valid_k:
            assert 0 <= v <= 100

    def test_constant_prices(self):
        candles = _make_candles([50.0] * 20)
        result = stochastic(candles, k_period=14, d_period=3)
        valid_k = [v for v in result["k"] if v is not None]
        for v in valid_k:
            assert v == pytest.approx(50.0)


# ------------------------------------------------------------------
# Bollinger Bands
# ------------------------------------------------------------------


class TestBollingerBands:
    def test_returns_three_bands(self):
        candles = _make_candles([100 + i % 5 for i in range(30)])
        result = bollinger_bands(candles, period=20)
        assert "upper" in result
        assert "middle" in result
        assert "lower" in result

    def test_upper_ge_middle_ge_lower(self):
        candles = _make_candles([100 + i % 5 for i in range(30)])
        result = bollinger_bands(candles, period=20)
        for i in range(len(candles)):
            if result["upper"][i] is not None:
                assert result["upper"][i] >= result["middle"][i]
                assert result["middle"][i] >= result["lower"][i]

    def test_constant_prices_no_band_width(self):
        candles = _make_candles([100.0] * 25)
        result = bollinger_bands(candles, period=20)
        for i in range(19, 25):
            assert result["upper"][i] == pytest.approx(100.0)
            assert result["middle"][i] == pytest.approx(100.0)
            assert result["lower"][i] == pytest.approx(100.0)


# ------------------------------------------------------------------
# ATR
# ------------------------------------------------------------------


class TestATR:
    def test_basic(self):
        candles = _make_candles(
            closes=[10, 11, 12, 11, 10, 11, 12, 13, 12, 11,
                    10, 11, 12, 13, 14],
            highs=[11, 12, 13, 12, 11, 12, 13, 14, 13, 12,
                   11, 12, 13, 14, 15],
            lows=[9, 10, 11, 10, 9, 10, 11, 12, 11, 10,
                  9, 10, 11, 12, 13],
        )
        result = atr(candles, period=14)
        assert result[-1] is not None
        assert result[-1] > 0

    def test_insufficient_data(self):
        candles = _make_candles([10, 20, 30])
        result = atr(candles, period=14)
        assert all(v is None for v in result)

    def test_positive_values(self):
        candles = _make_candles(list(range(10, 40)))
        result = atr(candles, period=14)
        valid = [v for v in result if v is not None]
        for v in valid:
            assert v > 0


# ------------------------------------------------------------------
# VWAP
# ------------------------------------------------------------------


class TestVWAP:
    def test_basic(self):
        candles = _make_candles([100, 101, 102])
        result = vwap(candles)
        assert all(v is not None for v in result)

    def test_single_candle(self):
        candles = _make_candles([50.0])
        result = vwap(candles)
        assert result[0] is not None

    def test_empty(self):
        result = vwap([])
        assert result == []


# ------------------------------------------------------------------
# OBV
# ------------------------------------------------------------------


class TestOBV:
    def test_up_day_adds_volume(self):
        candles = _make_candles([10, 12, 11], volumes=[100, 200, 150])
        result = obv(candles)
        assert result[0] == 100
        assert result[1] == 300   # price up → add
        assert result[2] == 150   # price down → subtract

    def test_flat_day_no_change(self):
        candles = _make_candles([10, 10, 10], volumes=[100, 200, 300])
        result = obv(candles)
        assert result[0] == 100
        assert result[1] == 100
        assert result[2] == 100

    def test_empty(self):
        result = obv([])
        assert result == []


# ------------------------------------------------------------------
# compute_indicators
# ------------------------------------------------------------------


class TestComputeIndicators:
    def test_multiple_indicators(self):
        candles = _make_candles(list(range(1, 50)))
        result = compute_indicators(candles, [
            {"name": "rsi", "period": 14},
            {"name": "sma", "period": 20},
        ])
        assert "rsi_14" in result
        assert "sma_20" in result
        assert "latest" in result["rsi_14"]
        assert "history" in result["rsi_14"]

    def test_unknown_indicator(self):
        candles = _make_candles([1, 2, 3])
        result = compute_indicators(candles, [{"name": "nonexistent"}])
        assert "error" in result["nonexistent"]

    def test_multi_output_indicator(self):
        candles = _make_candles(list(range(1, 50)))
        result = compute_indicators(candles, [{"name": "macd"}])
        macd_key = [k for k in result if k.startswith("macd")][0]
        assert "macd_line" in result[macd_key]
        assert "signal" in result[macd_key]
        assert "histogram" in result[macd_key]

    def test_history_length(self):
        candles = _make_candles(list(range(1, 50)))
        result = compute_indicators(
            candles, [{"name": "sma", "period": 5}], history_length=3,
        )
        assert len(result["sma_5"]["history"]) == 3

    def test_bollinger_output(self):
        candles = _make_candles([100 + i % 5 for i in range(30)])
        result = compute_indicators(candles, [
            {"name": "bollinger_bands", "period": 20},
        ])
        bb_key = [k for k in result if k.startswith("bollinger")][0]
        assert "upper" in result[bb_key]
        assert "middle" in result[bb_key]
        assert "lower" in result[bb_key]

    def test_stochastic_output(self):
        candles = _make_candles(list(range(1, 30)))
        result = compute_indicators(candles, [
            {"name": "stochastic", "k_period": 14, "d_period": 3},
        ])
        stoch_key = [k for k in result if k.startswith("stochastic")][0]
        assert "k" in result[stoch_key]
        assert "d" in result[stoch_key]

    def test_missing_name_skipped(self):
        candles = _make_candles([1, 2, 3])
        result = compute_indicators(candles, [{}])
        assert result == {}
