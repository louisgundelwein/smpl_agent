"""Hyperliquid perpetual futures trading tool."""

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

from src.hyperliquid_store import HyperliquidStore
from src.tools.base import Tool

# Max candles returned to avoid overwhelming the context window.
_MAX_CANDLES = 200


class _RateLimiter:
    """Sliding window rate limiter for Hyperliquid API."""

    def __init__(self, max_weight: int = 1200, window_seconds: int = 60) -> None:
        self._max_weight = max_weight
        self._window = window_seconds
        self._calls: list[tuple[float, int]] = []
        self._lock = threading.Lock()

    def wait_if_needed(self, weight: int) -> None:
        with self._lock:
            now = time.monotonic()
            self._calls = [(t, w) for t, w in self._calls if now - t < self._window]
            total = sum(w for _, w in self._calls)
            if total + weight > self._max_weight:
                if self._calls:
                    oldest = self._calls[0][0]
                    sleep_time = self._window - (now - oldest)
                    if sleep_time > 0:
                        time.sleep(sleep_time)
            self._calls.append((time.monotonic(), weight))


class HyperliquidTool(Tool):
    """Trade on Hyperliquid (perpetual futures).

    Supports market/limit orders, TP/SL, position management,
    market data queries, and strategy state persistence.
    """

    def __init__(
        self,
        store: HyperliquidStore,
        wallet_key: str,
        wallet_address: str,
        testnet: bool = True,
        max_position_size_usd: float = 10_000.0,
        max_loss_usd: float = 1_000.0,
        max_leverage: int = 20,
        scheduler_store: Any | None = None,
    ) -> None:
        self._store = store
        self._address = wallet_address
        self._testnet = testnet
        self._max_position_size_usd = max_position_size_usd
        self._max_loss_usd = max_loss_usd
        self._max_leverage = max_leverage
        self._rate_limiter = _RateLimiter()
        self._scheduler_store = scheduler_store

        base_url = constants.TESTNET_API_URL if testnet else constants.MAINNET_API_URL
        account = Account.from_key(wallet_key)
        self._info = Info(base_url, skip_ws=True)
        self._exchange = Exchange(account, base_url, account_address=wallet_address)

    @property
    def name(self) -> str:
        return "hyperliquid"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Trade on Hyperliquid (crypto perpetual futures exchange). "
                    "Query positions, market data, place/cancel orders with TP/SL, "
                    "and manage trading strategies. "
                    f"Currently on {'TESTNET' if self._testnet else 'MAINNET'}."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "get_positions", "get_open_orders", "get_fills",
                                "get_price", "get_orderbook", "get_candles",
                                "get_indicators", "get_funding_rate", "get_account_summary",
                                "place_order", "place_order_with_tpsl",
                                "market_open", "market_close", "cancel_order",
                                "set_leverage",
                                "get_trade_history", "save_strategy", "get_strategy",
                                "create_strategy", "activate_strategy", "deactivate_strategy",
                                "delete_strategy", "list_strategies",
                                "strategy_performance",
                                "log_strategy_execution", "strategy_execution_log",
                            ],
                            "description": (
                                "Action to perform. "
                                "Info: get_positions, get_open_orders, get_fills, get_account_summary. "
                                "Market data: get_price, get_orderbook, get_candles, get_indicators, get_funding_rate. "
                                "Trading: place_order, place_order_with_tpsl, market_open, market_close, cancel_order. "
                                "Config: set_leverage. "
                                "Strategy: get_trade_history, save_strategy, get_strategy, "
                                "create_strategy, activate_strategy, deactivate_strategy, "
                                "delete_strategy, list_strategies, strategy_performance, "
                                "log_strategy_execution, strategy_execution_log."
                            ),
                        },
                        "coin": {
                            "type": "string",
                            "description": "Trading pair symbol (e.g. 'ETH', 'BTC', 'SOL').",
                        },
                        "is_buy": {
                            "type": "boolean",
                            "description": "True for long/buy, False for short/sell.",
                        },
                        "size": {
                            "type": "number",
                            "description": "Position size in coin units.",
                        },
                        "price": {
                            "type": "number",
                            "description": "Limit price (for limit orders).",
                        },
                        "order_type": {
                            "type": "string",
                            "enum": ["market", "limit"],
                            "description": "Order type (default: 'limit').",
                        },
                        "slippage": {
                            "type": "number",
                            "description": "Max slippage for market orders (default: 0.01 = 1%).",
                        },
                        "take_profit_price": {
                            "type": "number",
                            "description": "Take-profit trigger price (for place_order_with_tpsl).",
                        },
                        "stop_loss_price": {
                            "type": "number",
                            "description": "Stop-loss trigger price (for place_order_with_tpsl).",
                        },
                        "order_id": {
                            "type": "integer",
                            "description": "Order ID (for cancel_order).",
                        },
                        "leverage": {
                            "type": "integer",
                            "description": "Leverage multiplier (for set_leverage).",
                        },
                        "is_cross": {
                            "type": "boolean",
                            "description": "True for cross margin, False for isolated (default: True).",
                        },
                        "interval": {
                            "type": "string",
                            "description": "Candle interval: '1m','5m','15m','1h','4h','1d'.",
                        },
                        "lookback_hours": {
                            "type": "integer",
                            "description": "Hours of candle data to fetch (default: 24).",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results for history queries (default: 50).",
                        },
                        "strategy_name": {
                            "type": "string",
                            "description": "Strategy name (for save/get strategy).",
                        },
                        "strategy_state": {
                            "type": "object",
                            "description": "Strategy state JSON (for save_strategy).",
                        },
                        "indicators": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": (
                                "List of indicator configs for get_indicators. "
                                "Each: {\"name\": \"rsi\", \"period\": 14}. "
                                "Available: sma, ema, macd, rsi, stochastic, "
                                "bollinger_bands, atr, vwap, obv."
                            ),
                        },
                        "description": {
                            "type": "string",
                            "description": "Strategy description (for create_strategy).",
                        },
                        "coins": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Coins the strategy trades (for create_strategy).",
                        },
                        "schedule": {
                            "type": "string",
                            "description": "Cron or interval for strategy execution (e.g. 'every 5m', '0 */4 * * *').",
                        },
                        "parameters": {
                            "type": "object",
                            "description": "Strategy parameters: entry/exit conditions, position sizing, risk management.",
                        },
                        "deliver_to": {
                            "type": "string",
                            "enum": ["memory", "telegram", "both"],
                            "description": "Where to deliver strategy execution results (default: 'memory').",
                        },
                        "telegram_chat_id": {
                            "type": "integer",
                            "description": "Telegram chat ID for strategy result delivery.",
                        },
                        "signals": {
                            "type": "object",
                            "description": "Indicator signals at execution time (for log_strategy_execution).",
                        },
                        "actions_taken": {
                            "type": "object",
                            "description": "Actions taken during execution (for log_strategy_execution).",
                        },
                        "notes": {
                            "type": "string",
                            "description": "Agent reasoning notes (for log_strategy_execution).",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        try:
            if action == "get_positions":
                return self._get_positions()
            elif action == "get_open_orders":
                return self._get_open_orders()
            elif action == "get_fills":
                return self._get_fills(kwargs)
            elif action == "get_price":
                return self._get_price(kwargs)
            elif action == "get_orderbook":
                return self._get_orderbook(kwargs)
            elif action == "get_candles":
                return self._get_candles(kwargs)
            elif action == "get_indicators":
                return self._get_indicators(kwargs)
            elif action == "get_funding_rate":
                return self._get_funding_rate(kwargs)
            elif action == "get_account_summary":
                return self._get_account_summary()
            elif action == "place_order":
                return self._place_order(kwargs)
            elif action == "place_order_with_tpsl":
                return self._place_order_with_tpsl(kwargs)
            elif action == "market_open":
                return self._market_open(kwargs)
            elif action == "market_close":
                return self._market_close(kwargs)
            elif action == "cancel_order":
                return self._cancel_order(kwargs)
            elif action == "set_leverage":
                return self._set_leverage(kwargs)
            elif action == "get_trade_history":
                return self._get_trade_history(kwargs)
            elif action == "save_strategy":
                return self._save_strategy(kwargs)
            elif action == "get_strategy":
                return self._get_strategy(kwargs)
            elif action == "create_strategy":
                return self._create_strategy(kwargs)
            elif action == "activate_strategy":
                return self._toggle_strategy(kwargs, active=True)
            elif action == "deactivate_strategy":
                return self._toggle_strategy(kwargs, active=False)
            elif action == "delete_strategy":
                return self._delete_strategy(kwargs)
            elif action == "list_strategies":
                return self._list_strategies()
            elif action == "strategy_performance":
                return self._strategy_performance(kwargs)
            elif action == "log_strategy_execution":
                return self._log_strategy_execution(kwargs)
            elif action == "strategy_execution_log":
                return self._strategy_execution_log(kwargs)
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _tag(self, data: dict) -> dict:
        """Add network tag to response."""
        data["network"] = "TESTNET" if self._testnet else "MAINNET"
        return data

    def _pre_trade_check(self, coin: str, size: float) -> str | None:
        """Validate trade against safety limits. Returns error string or None."""
        # Position size check
        self._rate_limiter.wait_if_needed(20)
        mid_prices = self._info.all_mids()
        mid = float(mid_prices.get(coin, 0))
        if mid == 0:
            return f"Cannot determine price for {coin}"
        notional = size * mid
        if notional > self._max_position_size_usd:
            return (
                f"Position size ${notional:.0f} exceeds limit "
                f"${self._max_position_size_usd:.0f}"
            )

        # Daily loss check (realized + unrealized)
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        today_trades = self._store.get_trades(after=today_start)
        realized_pnl = sum(t.get("pnl", 0) or 0 for t in today_trades)

        # Include unrealized PnL from open positions
        unrealized_pnl = 0.0
        try:
            self._rate_limiter.wait_if_needed(20)
            state = self._info.user_state(self._address)
            for pos in state.get("assetPositions", []):
                entry = pos.get("position", {})
                unrealized_pnl += float(entry.get("unrealizedPnl", 0))
        except Exception:
            pass  # Conservative: skip if we can't fetch, rely on realized only

        daily_pnl = realized_pnl + unrealized_pnl
        if daily_pnl < -self._max_loss_usd:
            return (
                f"Daily loss ${abs(daily_pnl):.0f} (realized: ${abs(realized_pnl):.0f}, "
                f"unrealized: ${abs(unrealized_pnl):.0f}) exceeds limit "
                f"${self._max_loss_usd:.0f}. Trading halted."
            )

        return None

    # ------------------------------------------------------------------
    # Info actions
    # ------------------------------------------------------------------

    def _get_positions(self) -> str:
        self._rate_limiter.wait_if_needed(20)
        state = self._info.user_state(self._address)

        # Auto-save snapshot
        margin = state.get("marginSummary", {})
        self._store.save_snapshot(
            snapshot=state,
            total_pnl=float(margin.get("totalRawUsd", 0)) if margin else None,
            account_value=float(margin.get("accountValue", 0)) if margin else None,
            margin_used=float(margin.get("totalMarginUsed", 0)) if margin else None,
        )

        return json.dumps(self._tag({"positions": state}), ensure_ascii=False)

    def _get_open_orders(self) -> str:
        self._rate_limiter.wait_if_needed(20)
        orders = self._info.open_orders(self._address)
        return json.dumps(self._tag({"open_orders": orders, "count": len(orders)}), ensure_ascii=False)

    def _get_fills(self, kw: dict) -> str:
        self._rate_limiter.wait_if_needed(20)
        fills = self._info.user_fills(self._address)
        limit = kw.get("limit", 50)
        return json.dumps(self._tag({"fills": fills[:limit], "count": len(fills[:limit])}), ensure_ascii=False)

    # ------------------------------------------------------------------
    # Market data actions
    # ------------------------------------------------------------------

    def _get_price(self, kw: dict) -> str:
        self._rate_limiter.wait_if_needed(20)
        mids = self._info.all_mids()
        coin = kw.get("coin")
        if coin:
            price = mids.get(coin)
            if price is None:
                return json.dumps(self._tag({"error": f"Unknown coin: {coin}"}))
            return json.dumps(self._tag({"coin": coin, "mid_price": price}))
        return json.dumps(self._tag({"prices": mids}), ensure_ascii=False)

    def _get_orderbook(self, kw: dict) -> str:
        coin = kw.get("coin")
        if not coin:
            return json.dumps({"error": "coin is required for get_orderbook"})
        self._rate_limiter.wait_if_needed(20)
        book = self._info.l2_snapshot(coin)
        return json.dumps(self._tag({"coin": coin, "orderbook": book}), ensure_ascii=False)

    def _get_candles(self, kw: dict) -> str:
        coin = kw.get("coin")
        if not coin:
            return json.dumps({"error": "coin is required for get_candles"})
        interval = kw.get("interval", "1h")
        lookback_hours = kw.get("lookback_hours", 24)

        now_ms = int(time.time() * 1000)
        start_ms = now_ms - lookback_hours * 3600 * 1000

        self._rate_limiter.wait_if_needed(20)
        candles = self._info.candles_snapshot(coin, interval, start_ms, now_ms)

        # Truncate to avoid context overflow
        if len(candles) > _MAX_CANDLES:
            candles = candles[-_MAX_CANDLES:]

        return json.dumps(
            self._tag({"coin": coin, "interval": interval, "candles": candles, "count": len(candles)}),
            ensure_ascii=False,
        )

    # ------------------------------------------------------------------
    # Trading actions
    # ------------------------------------------------------------------

    def _place_order(self, kw: dict) -> str:
        coin = kw.get("coin")
        is_buy = kw.get("is_buy")
        size = kw.get("size")
        price = kw.get("price")
        order_type = kw.get("order_type", "limit")

        if not all([coin, is_buy is not None, size, price is not None]):
            return json.dumps({"error": "coin, is_buy, size, and price are required for place_order"})

        check = self._pre_trade_check(coin, size)
        if check:
            return json.dumps(self._tag({"error": check}))

        if order_type == "market":
            ot = {"limit": {"tif": "Ioc"}}
        else:
            ot = {"limit": {"tif": "Gtc"}}

        self._rate_limiter.wait_if_needed(1)
        result = self._exchange.order(coin, is_buy, size, price, ot)

        self._store.log_trade(
            coin=coin, action="order_placed",
            side="buy" if is_buy else "sell",
            size=size, price=price, order_type=order_type,
            metadata=result,
        )

        return json.dumps(self._tag({"order_result": result}), ensure_ascii=False)

    def _place_order_with_tpsl(self, kw: dict) -> str:
        coin = kw.get("coin")
        is_buy = kw.get("is_buy")
        size = kw.get("size")
        price = kw.get("price")
        tp_price = kw.get("take_profit_price")
        sl_price = kw.get("stop_loss_price")

        if not all([coin, is_buy is not None, size, price is not None]):
            return json.dumps({"error": "coin, is_buy, size, and price are required"})
        if not tp_price and not sl_price:
            return json.dumps({"error": "At least one of take_profit_price or stop_loss_price is required"})

        check = self._pre_trade_check(coin, size)
        if check:
            return json.dumps(self._tag({"error": check}))

        exit_side = not is_buy
        orders = [
            {
                "coin": coin,
                "is_buy": is_buy,
                "sz": size,
                "limit_px": price,
                "order_type": {"limit": {"tif": "Gtc"}},
                "reduce_only": False,
            },
        ]

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

        self._rate_limiter.wait_if_needed(1)
        result = self._exchange.bulk_orders(orders, grouping="normalTpsl")

        self._store.log_trade(
            coin=coin, action="order_placed_tpsl",
            side="buy" if is_buy else "sell",
            size=size, price=price, order_type="limit+tpsl",
            metadata={"result": result, "tp": tp_price, "sl": sl_price},
        )

        return json.dumps(self._tag({"order_result": result}), ensure_ascii=False)

    def _market_open(self, kw: dict) -> str:
        coin = kw.get("coin")
        is_buy = kw.get("is_buy")
        size = kw.get("size")
        slippage = kw.get("slippage", 0.01)

        if not all([coin, is_buy is not None, size]):
            return json.dumps({"error": "coin, is_buy, and size are required for market_open"})

        check = self._pre_trade_check(coin, size)
        if check:
            return json.dumps(self._tag({"error": check}))

        self._rate_limiter.wait_if_needed(1)
        result = self._exchange.market_open(coin, is_buy, size, slippage)

        self._store.log_trade(
            coin=coin, action="market_open",
            side="buy" if is_buy else "sell",
            size=size, order_type="market",
            metadata={"result": result, "slippage": slippage},
        )

        return json.dumps(self._tag({"market_open_result": result}), ensure_ascii=False)

    def _market_close(self, kw: dict) -> str:
        coin = kw.get("coin")
        slippage = kw.get("slippage", 0.01)

        if not coin:
            return json.dumps({"error": "coin is required for market_close"})

        self._rate_limiter.wait_if_needed(1)
        result = self._exchange.market_close(coin, slippage=slippage)

        self._store.log_trade(
            coin=coin, action="market_close",
            order_type="market",
            metadata={"result": result, "slippage": slippage},
        )

        return json.dumps(self._tag({"market_close_result": result}), ensure_ascii=False)

    def _cancel_order(self, kw: dict) -> str:
        coin = kw.get("coin")
        order_id = kw.get("order_id")

        if not all([coin, order_id is not None]):
            return json.dumps({"error": "coin and order_id are required for cancel_order"})

        self._rate_limiter.wait_if_needed(1)
        result = self._exchange.cancel(coin, order_id)

        self._store.log_trade(
            coin=coin, action="order_cancelled",
            trade_id=str(order_id),
            metadata=result,
        )

        return json.dumps(self._tag({"cancel_result": result}), ensure_ascii=False)

    # ------------------------------------------------------------------
    # Config actions
    # ------------------------------------------------------------------

    def _set_leverage(self, kw: dict) -> str:
        coin = kw.get("coin")
        leverage = kw.get("leverage")
        is_cross = kw.get("is_cross", True)

        if not all([coin, leverage is not None]):
            return json.dumps({"error": "coin and leverage are required for set_leverage"})

        if leverage > self._max_leverage:
            return json.dumps(self._tag({
                "error": f"Leverage {leverage}x exceeds max allowed {self._max_leverage}x"
            }))

        self._rate_limiter.wait_if_needed(1)
        result = self._exchange.update_leverage(leverage, coin, is_cross)

        return json.dumps(self._tag({"leverage_result": result, "coin": coin, "leverage": leverage}), ensure_ascii=False)

    # ------------------------------------------------------------------
    # Strategy / history actions (store-backed)
    # ------------------------------------------------------------------

    def _get_trade_history(self, kw: dict) -> str:
        coin = kw.get("coin")
        limit = kw.get("limit", 50)
        trades = self._store.get_trades(coin=coin, limit=limit)
        summary = self._store.get_trade_summary(coin=coin)
        return json.dumps(self._tag({"trades": trades, "summary": summary}), ensure_ascii=False)

    def _save_strategy(self, kw: dict) -> str:
        name = kw.get("strategy_name")
        state = kw.get("strategy_state")
        if not name or state is None:
            return json.dumps({"error": "strategy_name and strategy_state are required"})
        sid = self._store.save_strategy(name, state)
        return json.dumps(self._tag({"saved": True, "strategy_id": sid, "name": name}))

    def _get_strategy(self, kw: dict) -> str:
        name = kw.get("strategy_name")
        if not name:
            # List all strategies
            strats = self._store.list_strategies()
            return json.dumps(self._tag({"strategies": strats, "count": len(strats)}), ensure_ascii=False)
        strat = self._store.get_strategy(name)
        if strat is None:
            return json.dumps(self._tag({"error": f"Strategy '{name}' not found"}))
        return json.dumps(self._tag({"strategy": strat}), ensure_ascii=False)

    # ------------------------------------------------------------------
    # Market data (extended)
    # ------------------------------------------------------------------

    def _get_indicators(self, kw: dict) -> str:
        coin = kw.get("coin")
        if not coin:
            return json.dumps({"error": "coin is required for get_indicators"})
        indicators = kw.get("indicators")
        if not indicators:
            return json.dumps({"error": "indicators list is required for get_indicators"})
        interval = kw.get("interval", "1h")
        lookback_hours = kw.get("lookback_hours", 48)

        now_ms = int(time.time() * 1000)
        start_ms = now_ms - lookback_hours * 3600 * 1000

        self._rate_limiter.wait_if_needed(20)
        candles = self._info.candles_snapshot(coin, interval, start_ms, now_ms)

        if not candles:
            return json.dumps(self._tag({"error": f"No candle data for {coin}"}))

        from src.indicators import compute_indicators
        results = compute_indicators(candles, indicators, history_length=10)

        current_price = float(candles[-1]["c"])
        return json.dumps(self._tag({
            "coin": coin,
            "interval": interval,
            "current_price": current_price,
            "candle_count": len(candles),
            "indicators": results,
        }), ensure_ascii=False)

    def _get_funding_rate(self, kw: dict) -> str:
        coin = kw.get("coin")
        if not coin:
            return json.dumps({"error": "coin is required for get_funding_rate"})

        self._rate_limiter.wait_if_needed(20)
        meta_ctx = self._info.meta_and_asset_ctxs()

        universe = meta_ctx[0]["universe"]
        asset_ctxs = meta_ctx[1]

        for i, asset_info in enumerate(universe):
            if asset_info["name"] == coin:
                ctx = asset_ctxs[i]
                funding = float(ctx.get("funding", "0"))
                premium = float(ctx.get("premium", "0")) if ctx.get("premium") else None
                annualized = funding * 8760 * 100  # as percentage
                return json.dumps(self._tag({
                    "coin": coin,
                    "current_funding_rate": funding,
                    "current_funding_rate_pct": f"{funding * 100:.4f}%",
                    "predicted_premium": premium,
                    "annualized_rate_pct": f"{annualized:.2f}%",
                    "mark_price": ctx.get("markPx"),
                    "oracle_price": ctx.get("oraclePx"),
                    "open_interest": ctx.get("openInterest"),
                }), ensure_ascii=False)

        return json.dumps(self._tag({"error": f"Coin {coin} not found in metadata"}))

    def _get_account_summary(self) -> str:
        self._rate_limiter.wait_if_needed(20)
        state = self._info.user_state(self._address)

        margin = state.get("marginSummary", {})
        positions = state.get("assetPositions", [])

        active_positions = []
        total_unrealized = 0.0
        for pos in positions:
            entry = pos.get("position", {})
            szi = float(entry.get("szi", "0"))
            if szi != 0:
                unrealized = float(entry.get("unrealizedPnl", "0"))
                total_unrealized += unrealized
                active_positions.append({
                    "coin": entry.get("coin"),
                    "size": szi,
                    "entry_price": entry.get("entryPx"),
                    "unrealized_pnl": unrealized,
                    "leverage": entry.get("leverage"),
                })

        # Daily PnL from trade log
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        today_trades = self._store.get_trades(after=today_start)
        daily_realized_pnl = sum(t.get("pnl", 0) or 0 for t in today_trades)

        return json.dumps(self._tag({
            "account_value": margin.get("accountValue"),
            "total_margin_used": margin.get("totalMarginUsed"),
            "total_raw_usd": margin.get("totalRawUsd"),
            "withdrawable": state.get("withdrawable"),
            "active_positions": active_positions,
            "position_count": len(active_positions),
            "total_unrealized_pnl": total_unrealized,
            "daily_realized_pnl": daily_realized_pnl,
            "daily_total_pnl": daily_realized_pnl + total_unrealized,
        }), ensure_ascii=False)

    # ------------------------------------------------------------------
    # Strategy lifecycle
    # ------------------------------------------------------------------

    def _create_strategy(self, kw: dict) -> str:
        name = kw.get("strategy_name")
        description = kw.get("description", "")
        coins = kw.get("coins", [])
        schedule = kw.get("schedule")
        parameters = kw.get("parameters", {})
        deliver_to = kw.get("deliver_to", "memory")
        telegram_chat_id = kw.get("telegram_chat_id")

        if not name:
            return json.dumps({"error": "strategy_name is required"})
        if not schedule:
            return json.dumps({"error": "schedule is required for create_strategy"})

        # Validate schedule
        from src.scheduler import compute_next_run
        try:
            compute_next_run(schedule)
        except Exception as exc:
            return json.dumps({"error": f"Invalid schedule: {exc}"})

        scheduler_task_name = f"strategy-{name}"
        now = datetime.now(timezone.utc).isoformat()

        strategy_state = {
            "description": description,
            "coins": coins,
            "status": "active",
            "schedule": schedule,
            "scheduler_task_name": scheduler_task_name,
            "parameters": parameters,
            "runtime_state": {},
            "created_at": now,
            "last_executed_at": None,
        }

        sid = self._store.save_strategy(name, strategy_state)

        prompt = self._build_strategy_prompt(name, strategy_state)

        scheduler_result = None
        if self._scheduler_store:
            try:
                task_id = self._scheduler_store.add(
                    name=scheduler_task_name,
                    prompt=prompt,
                    cron_expression=schedule,
                    deliver_to=deliver_to,
                    telegram_chat_id=telegram_chat_id,
                )
                task = self._scheduler_store.get(scheduler_task_name)
                scheduler_result = {
                    "task_id": task_id,
                    "next_run_at": task["next_run_at"] if task else None,
                }
            except Exception as exc:
                scheduler_result = {"error": str(exc)}

        return json.dumps(self._tag({
            "created": True,
            "strategy_id": sid,
            "name": name,
            "schedule": schedule,
            "scheduler_task": scheduler_result,
        }), ensure_ascii=False)

    def _build_strategy_prompt(self, name: str, state: dict) -> str:
        """Build the prompt the scheduler uses to trigger strategy execution."""
        coins_str = ", ".join(state.get("coins", [])) or "as defined in strategy"
        params_str = json.dumps(state.get("parameters", {}))
        return (
            f"[Strategy execution '{name}']: Execute the trading strategy '{name}'.\n\n"
            f"Strategy: {state.get('description', 'No description')}\n"
            f"Coins: {coins_str}\n"
            f"Parameters: {params_str}\n\n"
            f"Instructions:\n"
            f"1. Load current strategy state: hyperliquid get_strategy (strategy_name='{name}')\n"
            f"2. Check market conditions: hyperliquid get_indicators for each coin\n"
            f"3. Check account: hyperliquid get_account_summary\n"
            f"4. Evaluate signals against strategy parameters\n"
            f"5. Execute trades if entry/exit conditions are met\n"
            f"6. Log execution: hyperliquid log_strategy_execution\n"
            f"7. Update runtime state: hyperliquid save_strategy\n"
        )

    def _toggle_strategy(self, kw: dict, active: bool) -> str:
        name = kw.get("strategy_name")
        if not name:
            return json.dumps({"error": "strategy_name is required"})

        strat = self._store.get_strategy(name)
        if not strat:
            return json.dumps(self._tag({"error": f"Strategy '{name}' not found"}))

        state = strat["state"]
        state["status"] = "active" if active else "inactive"
        self._store.save_strategy(name, state)

        scheduler_toggled = False
        task_name = state.get("scheduler_task_name")
        if task_name and self._scheduler_store:
            scheduler_toggled = self._scheduler_store.toggle(task_name, enabled=active)

        action_word = "activated" if active else "deactivated"
        return json.dumps(self._tag({
            action_word: True,
            "name": name,
            "status": state["status"],
            "scheduler_toggled": scheduler_toggled,
        }))

    def _delete_strategy(self, kw: dict) -> str:
        name = kw.get("strategy_name")
        if not name:
            return json.dumps({"error": "strategy_name is required"})

        strat = self._store.get_strategy(name)
        scheduler_deleted = False
        if strat:
            state = strat["state"]
            task_name = state.get("scheduler_task_name")
            if task_name and self._scheduler_store:
                scheduler_deleted = self._scheduler_store.delete(task_name)

        deleted = self._store.delete_strategy(name)
        return json.dumps(self._tag({
            "deleted": deleted,
            "name": name,
            "scheduler_deleted": scheduler_deleted,
        }))

    def _list_strategies(self) -> str:
        strats = self._store.list_strategies()
        enriched = []
        for s in strats:
            full = self._store.get_strategy(s["name"])
            state = full["state"] if full else {}
            enriched.append({
                "name": s["name"],
                "description": state.get("description", ""),
                "status": state.get("status", "unknown"),
                "coins": state.get("coins", []),
                "schedule": state.get("schedule", ""),
                "last_executed_at": state.get("last_executed_at"),
                "updated_at": s.get("updated_at"),
            })
        return json.dumps(self._tag({
            "strategies": enriched,
            "count": len(enriched),
        }), ensure_ascii=False)

    # ------------------------------------------------------------------
    # Strategy performance and execution logging
    # ------------------------------------------------------------------

    def _strategy_performance(self, kw: dict) -> str:
        name = kw.get("strategy_name")
        if not name:
            return json.dumps({"error": "strategy_name is required"})
        perf = self._store.get_strategy_performance(name)
        return json.dumps(self._tag({
            "strategy_name": name,
            "performance": perf,
        }), ensure_ascii=False)

    def _log_strategy_execution(self, kw: dict) -> str:
        name = kw.get("strategy_name")
        if not name:
            return json.dumps({"error": "strategy_name is required"})

        signals = kw.get("signals")
        actions = kw.get("actions_taken")
        notes = kw.get("notes")

        # Snapshot current PnL
        pnl_snapshot = None
        try:
            self._rate_limiter.wait_if_needed(20)
            state = self._info.user_state(self._address)
            margin = state.get("marginSummary", {})
            pnl_snapshot = float(margin.get("totalRawUsd", 0))
        except Exception:
            pass

        eid = self._store.log_execution(
            strategy_name=name,
            signals=signals,
            actions=actions,
            pnl_snapshot=pnl_snapshot,
            notes=notes,
        )

        # Update last_executed_at
        strat = self._store.get_strategy(name)
        if strat:
            st = strat["state"]
            st["last_executed_at"] = datetime.now(timezone.utc).isoformat()
            self._store.save_strategy(name, st)

        return json.dumps(self._tag({
            "logged": True,
            "execution_id": eid,
            "strategy_name": name,
        }))

    def _strategy_execution_log(self, kw: dict) -> str:
        name = kw.get("strategy_name")
        if not name:
            return json.dumps({"error": "strategy_name is required"})
        limit = kw.get("limit", 20)
        executions = self._store.get_executions(name, limit=limit)
        return json.dumps(self._tag({
            "strategy_name": name,
            "executions": executions,
            "count": len(executions),
        }), ensure_ascii=False)
