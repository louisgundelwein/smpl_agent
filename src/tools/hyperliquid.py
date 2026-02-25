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
    ) -> None:
        self._store = store
        self._address = wallet_address
        self._testnet = testnet
        self._max_position_size_usd = max_position_size_usd
        self._max_loss_usd = max_loss_usd
        self._max_leverage = max_leverage
        self._rate_limiter = _RateLimiter()

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
                                "place_order", "place_order_with_tpsl",
                                "market_open", "market_close", "cancel_order",
                                "set_leverage",
                                "get_trade_history", "save_strategy", "get_strategy",
                            ],
                            "description": (
                                "Action to perform. Info: get_positions, get_open_orders, get_fills. "
                                "Market data: get_price, get_orderbook, get_candles. "
                                "Trading: place_order, place_order_with_tpsl, market_open, market_close, cancel_order. "
                                "Config: set_leverage. "
                                "Strategy: get_trade_history, save_strategy, get_strategy."
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
