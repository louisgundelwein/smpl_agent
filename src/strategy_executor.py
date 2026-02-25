"""Deterministic strategy executor — runs trading strategies without LLM.

Replaces the multi-round LLM loop for scheduled strategy execution.
Evaluates indicator-based entry/exit conditions and executes trades
in pure Python, consuming zero LLM tokens.
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

from src.indicators import compute_indicators

logger = logging.getLogger(__name__)

# Per-strategy locks to prevent concurrent execution of the same strategy.
_strategy_locks: dict[str, threading.Lock] = {}
_lock_guard = threading.Lock()


def _get_strategy_lock(name: str) -> threading.Lock:
    with _lock_guard:
        if name not in _strategy_locks:
            _strategy_locks[name] = threading.Lock()
        return _strategy_locks[name]


class StrategyExecutor:
    """Evaluates and executes trading strategies without LLM involvement.

    Operates directly on a HyperliquidTool instance's internals:
    _info, _exchange, _store, _rate_limiter, _pre_trade_check, _address.
    """

    def __init__(self, tool: Any) -> None:
        self._info = tool._info
        self._exchange = tool._exchange
        self._store = tool._store
        self._rate_limiter = tool._rate_limiter
        self._address = tool._address
        self._pre_trade_check = tool._pre_trade_check
        self._max_leverage = tool._max_leverage

    def execute(self, strategy_name: str) -> dict[str, Any]:
        """Execute a full strategy cycle.

        Returns a structured result dict (never raises).
        """
        lock = _get_strategy_lock(strategy_name)
        if not lock.acquire(timeout=60):
            return {"status": "skipped", "reason": f"Strategy '{strategy_name}' already executing"}
        try:
            return self._do_execute(strategy_name)
        except Exception as exc:
            logger.exception("Strategy '%s' execution failed", strategy_name)
            return {"status": "error", "error": str(exc)}
        finally:
            lock.release()

    # ------------------------------------------------------------------
    # Internal execution
    # ------------------------------------------------------------------

    def _do_execute(self, strategy_name: str) -> dict[str, Any]:
        # 1. Load strategy
        strat = self._store.get_strategy(strategy_name)
        if not strat:
            return {"status": "error", "error": f"Strategy '{strategy_name}' not found"}

        state = strat["state"]
        if state.get("status") != "active":
            return {"status": "skipped", "reason": "Strategy is not active"}

        params = state.get("parameters", {})
        coins = state.get("coins", [])
        if not coins:
            return {"status": "error", "error": "No coins configured"}

        interval = params.get("timeframe", "1h")
        lookback_hours = params.get("lookback_hours", 4)

        # 2. Fetch account state (single API call)
        self._rate_limiter.wait_if_needed(20)
        user_state = self._info.user_state(self._address)
        margin = user_state.get("marginSummary", {})
        account_value = float(margin.get("accountValue", 0))
        pnl_snapshot = float(margin.get("totalRawUsd", 0))

        positions_by_coin = self._extract_positions(user_state)

        # 3. Fetch indicators for each coin
        market_data = {}
        for coin in coins:
            md = self._fetch_coin_data(coin, params, interval, lookback_hours)
            if md:
                market_data[coin] = md

        if not market_data:
            return {"status": "error", "error": "Failed to fetch market data for all coins"}

        # 4. Evaluate signals and execute trades
        all_signals = {}
        all_actions = []
        notes_parts = []

        for coin in coins:
            if coin not in market_data:
                continue

            md = market_data[coin]
            position = positions_by_coin.get(coin)
            signal = self._evaluate_signal(coin, md, position, params)
            all_signals[coin] = signal

            if signal["action"] == "hold":
                notes_parts.append(f"{coin}: hold ({signal.get('reason', 'no signal')})")
                continue

            # 5. Execute trade
            trade_result = self._execute_trade(
                coin, signal, md, params, strategy_name,
            )
            all_actions.append(trade_result)
            notes_parts.append(
                f"{coin}: {signal['action']} → {trade_result.get('status', 'unknown')}"
            )

        # 6. Log execution
        self._store.log_execution(
            strategy_name=strategy_name,
            signals=all_signals,
            actions={"trades": all_actions} if all_actions else {"trades": []},
            pnl_snapshot=pnl_snapshot,
            notes="; ".join(notes_parts),
        )

        # 7. Update last_executed_at
        state["last_executed_at"] = datetime.now(timezone.utc).isoformat()
        self._store.save_strategy(strategy_name, state)

        return {
            "status": "executed",
            "signals": all_signals,
            "actions_taken": all_actions,
            "notes": "; ".join(notes_parts),
            "account_value": account_value,
        }

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_positions(user_state: dict) -> dict[str, dict]:
        """Extract active positions keyed by coin."""
        result = {}
        for pos in user_state.get("assetPositions", []):
            entry = pos.get("position", {})
            szi = float(entry.get("szi", "0"))
            if szi != 0:
                result[entry.get("coin")] = {
                    "size": szi,
                    "entry_price": float(entry.get("entryPx", "0")),
                    "unrealized_pnl": float(entry.get("unrealizedPnl", "0")),
                    "leverage": entry.get("leverage"),
                }
        return result

    def _fetch_coin_data(
        self,
        coin: str,
        params: dict,
        interval: str,
        lookback_hours: int,
    ) -> dict[str, Any] | None:
        """Fetch candles and compute indicators for a single coin."""
        try:
            now_ms = int(time.time() * 1000)
            start_ms = now_ms - lookback_hours * 3600 * 1000

            self._rate_limiter.wait_if_needed(20)
            candles = self._info.candles_snapshot(coin, interval, start_ms, now_ms)

            if not candles:
                return None

            # Build indicator configs from strategy params
            indicator_configs = self._build_indicator_configs(params)

            results = compute_indicators(candles, indicator_configs, history_length=1)

            current_price = float(candles[-1]["c"])
            return {
                "price": current_price,
                "indicators": {k: v.get("latest") if isinstance(v, dict) and "latest" in v else v
                               for k, v in results.items()},
                "candle_count": len(candles),
            }
        except Exception as exc:
            logger.warning("Failed to fetch data for %s: %s", coin, exc)
            return None

    @staticmethod
    def _build_indicator_configs(params: dict) -> list[dict]:
        """Build indicator configs from strategy parameters."""
        configs = []

        # Always include RSI if any RSI threshold is set
        rsi_period = params.get("rsi_period", 14)
        if any(k.startswith("rsi_") for k in params):
            configs.append({"name": "rsi", "period": rsi_period})

        # Always include ATR if stop_loss_atr_multiplier is set
        atr_period = params.get("atr_period", 14)
        if "stop_loss_atr_multiplier" in params:
            configs.append({"name": "atr", "period": atr_period})

        # Include MACD if any macd param is set
        if any(k.startswith("macd_") for k in params):
            configs.append({
                "name": "macd",
                "fast": params.get("macd_fast_period", 12),
                "slow": params.get("macd_slow_period", 26),
                "signal_period": params.get("macd_signal_period", 9),
            })

        # Include EMA if ema_period is set
        if "ema_period" in params:
            configs.append({"name": "ema", "period": params["ema_period"]})

        # Fallback: at least RSI + ATR
        if not configs:
            configs = [
                {"name": "rsi", "period": 14},
                {"name": "atr", "period": 14},
            ]

        return configs

    # ------------------------------------------------------------------
    # Signal evaluation
    # ------------------------------------------------------------------

    def _evaluate_signal(
        self,
        coin: str,
        market_data: dict,
        position: dict | None,
        params: dict,
    ) -> dict[str, Any]:
        """Evaluate entry/exit signals for a single coin."""
        indicators = market_data["indicators"]
        price = market_data["price"]

        rsi_val = self._get_indicator_value(indicators, "rsi")
        atr_val = self._get_indicator_value(indicators, "atr")

        # Extract MACD sub-values if present
        macd_data = {k: v for k, v in indicators.items() if k.startswith("macd")}
        macd_line = None
        macd_signal = None
        if macd_data:
            # macd indicator key is like "macd_12_26_9"
            for key, val in macd_data.items():
                if isinstance(val, dict):
                    if "macd_line" in val:
                        macd_line = val["macd_line"].get("latest") if isinstance(val["macd_line"], dict) else val["macd_line"]
                    if "signal" in val:
                        macd_signal = val["signal"].get("latest") if isinstance(val["signal"], dict) else val["signal"]

        rsi_entry = params.get("rsi_entry_threshold")
        rsi_exit = params.get("rsi_exit_overbought_threshold")

        signal_info = {
            "coin": coin,
            "price": price,
            "rsi": rsi_val,
            "atr": atr_val,
        }

        # --- Exit check (position exists) ---
        if position:
            is_long = position["size"] > 0
            if is_long and rsi_exit is not None and rsi_val is not None and rsi_val > rsi_exit:
                return {**signal_info, "action": "exit", "reason": f"RSI {rsi_val:.1f} > exit threshold {rsi_exit}"}

            # Short exit (RSI below inverse threshold)
            if not is_long and rsi_entry is not None and rsi_val is not None and rsi_val < rsi_entry:
                return {**signal_info, "action": "exit", "reason": f"RSI {rsi_val:.1f} < entry threshold (short exit)"}

            return {**signal_info, "action": "hold", "reason": "Position open, no exit signal"}

        # --- Entry check (no position) ---
        if rsi_entry is not None and rsi_val is not None and rsi_val < rsi_entry:
            return {**signal_info, "action": "enter_long", "reason": f"RSI {rsi_val:.1f} < entry threshold {rsi_entry}"}

        return {**signal_info, "action": "hold", "reason": "No entry signal"}

    @staticmethod
    def _get_indicator_value(indicators: dict, prefix: str) -> float | None:
        """Get the latest value for an indicator by name prefix."""
        for key, val in indicators.items():
            if key.startswith(prefix):
                if isinstance(val, dict):
                    return val.get("latest")
                if isinstance(val, (int, float)):
                    return float(val)
        return None

    # ------------------------------------------------------------------
    # Trade execution
    # ------------------------------------------------------------------

    def _execute_trade(
        self,
        coin: str,
        signal: dict,
        market_data: dict,
        params: dict,
        strategy_name: str,
    ) -> dict[str, Any]:
        """Execute a trade based on the signal."""
        action = signal["action"]
        price = market_data["price"]

        if action == "exit":
            return self._close_position(coin, strategy_name)

        if action == "enter_long":
            return self._open_position(
                coin, True, price, market_data, params, strategy_name,
            )

        if action == "enter_short":
            return self._open_position(
                coin, False, price, market_data, params, strategy_name,
            )

        return {"status": "no_action", "coin": coin}

    def _close_position(self, coin: str, strategy_name: str) -> dict[str, Any]:
        """Close an existing position."""
        try:
            slippage = 0.01
            self._rate_limiter.wait_if_needed(1)
            result = self._exchange.market_close(coin, slippage=slippage)

            self._store.log_trade(
                coin=coin, action="market_close", order_type="market",
                metadata={"result": result, "slippage": slippage},
                strategy_name=strategy_name,
            )

            return {"status": "closed", "coin": coin, "result": result}
        except Exception as exc:
            return {"status": "error", "coin": coin, "error": str(exc)}

    def _open_position(
        self,
        coin: str,
        is_buy: bool,
        price: float,
        market_data: dict,
        params: dict,
        strategy_name: str,
    ) -> dict[str, Any]:
        """Open a new position with optional TP/SL."""
        # Position sizing
        risk_usd = params.get("risk_per_trade_usd", 1.0)
        atr_val = market_data["indicators"].get("atr") or self._get_indicator_value(market_data["indicators"], "atr")
        sl_multiplier = params.get("stop_loss_atr_multiplier", 1.5)

        if atr_val and atr_val > 0 and price > 0:
            stop_distance = atr_val * sl_multiplier
            size = risk_usd / stop_distance
        else:
            # Fallback: use risk_usd / price as a tiny position
            size = risk_usd / price if price > 0 else 0

        if size <= 0:
            return {"status": "error", "coin": coin, "error": "Computed size is zero"}

        # Round size to reasonable precision
        size = round(size, 6)

        # Pre-trade safety check
        check = self._pre_trade_check(coin, size)
        if check:
            return {"status": "blocked", "coin": coin, "reason": check}

        # Set leverage
        leverage = params.get("leverage")
        if leverage:
            leverage = min(leverage, self._max_leverage)
            try:
                self._rate_limiter.wait_if_needed(1)
                self._exchange.update_leverage(leverage, coin, True)
            except Exception as exc:
                logger.warning("Failed to set leverage for %s: %s", coin, exc)

        # Compute TP/SL prices
        tp_price = None
        sl_price = None
        if atr_val and atr_val > 0:
            stop_distance = atr_val * sl_multiplier
            rr_ratio = params.get("take_profit_risk_reward_ratio", 1.5)
            if is_buy:
                sl_price = round(price - stop_distance, 2)
                tp_price = round(price + stop_distance * rr_ratio, 2)
            else:
                sl_price = round(price + stop_distance, 2)
                tp_price = round(price - stop_distance * rr_ratio, 2)

        # Execute
        try:
            slippage = 0.01
            self._rate_limiter.wait_if_needed(1)
            result = self._exchange.market_open(coin, is_buy, size, slippage)

            self._store.log_trade(
                coin=coin,
                action="market_open",
                side="buy" if is_buy else "sell",
                size=size,
                order_type="market",
                metadata={
                    "result": result,
                    "tp_price": tp_price,
                    "sl_price": sl_price,
                    "slippage": slippage,
                },
                strategy_name=strategy_name,
            )

            # Place TP/SL orders if computed
            tpsl_result = None
            if tp_price or sl_price:
                tpsl_result = self._place_tpsl(coin, not is_buy, size, tp_price, sl_price)

            return {
                "status": "opened",
                "coin": coin,
                "side": "buy" if is_buy else "sell",
                "size": size,
                "tp_price": tp_price,
                "sl_price": sl_price,
                "result": result,
                "tpsl": tpsl_result,
            }
        except Exception as exc:
            return {"status": "error", "coin": coin, "error": str(exc)}

    def _place_tpsl(
        self,
        coin: str,
        exit_side: bool,
        size: float,
        tp_price: float | None,
        sl_price: float | None,
    ) -> dict[str, Any] | None:
        """Place take-profit and/or stop-loss orders."""
        orders = []
        if tp_price:
            orders.append({
                "coin": coin,
                "is_buy": exit_side,
                "sz": size,
                "limit_px": tp_price,
                "order_type": {"trigger": {"triggerPx": str(tp_price), "isMarket": True, "tpsl": "tp"}},
                "reduce_only": True,
            })
        if sl_price:
            orders.append({
                "coin": coin,
                "is_buy": exit_side,
                "sz": size,
                "limit_px": sl_price,
                "order_type": {"trigger": {"triggerPx": str(sl_price), "isMarket": True, "tpsl": "sl"}},
                "reduce_only": True,
            })

        if not orders:
            return None

        try:
            self._rate_limiter.wait_if_needed(1)
            result = self._exchange.bulk_orders(orders, grouping="normalTpsl")
            return {"status": "placed", "result": result}
        except Exception as exc:
            logger.warning("Failed to place TP/SL for %s: %s", coin, exc)
            return {"status": "error", "error": str(exc)}
