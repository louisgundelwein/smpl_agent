"""Hyperliquid perpetual futures trading tool.

Optimised for minimal token consumption: composite actions return
compact human-readable text instead of raw JSON.
"""

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

# Absolute ceiling on characters returned to the LLM.
_MAX_OUTPUT_CHARS = 2000
# Max candles fetched from the API (internal use only).
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

    LLM-facing actions are consolidated into a small set of composite
    operations that return compact text.  Raw data methods are kept
    internally for the deterministic StrategyExecutor.
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

    # ------------------------------------------------------------------
    # Schema — compact, 7 actions instead of 24
    # ------------------------------------------------------------------

    @property
    def schema(self) -> dict[str, Any]:
        net = "TESTNET" if self._testnet else "MAINNET"
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    f"Hyperliquid perps ({net}). "
                    "status: account+positions+orders. "
                    "analyze: price+indicators+funding. "
                    "trade: open/close/limit/cancel. "
                    "history: recent trades. "
                    "strategy: manage automated strategies."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "status", "analyze", "trade", "history",
                                "strategy", "execute_strategy",
                            ],
                        },
                        "coin": {"type": "string", "description": "e.g. 'ETH'."},
                        "sub_action": {
                            "type": "string",
                            "description": (
                                "trade: open|close|limit_order|cancel. "
                                "strategy: create|list|get|activate|deactivate|delete|performance."
                            ),
                        },
                        "is_buy": {"type": "boolean", "description": "True=long, False=short."},
                        "size": {"type": "number", "description": "Size in coin units."},
                        "price": {"type": "number", "description": "Limit price."},
                        "take_profit_price": {"type": "number"},
                        "stop_loss_price": {"type": "number"},
                        "order_id": {"type": "integer"},
                        "leverage": {"type": "integer"},
                        "strategy_name": {"type": "string"},
                        "schedule": {"type": "string", "description": "Cron or interval."},
                        "coins": {"type": "array", "items": {"type": "string"}},
                        "parameters": {"type": "object", "description": "Strategy parameters."},
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
            # --- LLM-facing composite actions ---
            if action == "status":
                return self._action_status()
            if action == "analyze":
                return self._action_analyze(kwargs)
            if action == "trade":
                return self._action_trade(kwargs)
            if action == "history":
                return self._action_history(kwargs)
            if action == "strategy":
                return self._action_strategy(kwargs)

            # --- Preserved for scheduler direct_tool_call ---
            if action == "execute_strategy":
                return self._execute_strategy(kwargs)

            # --- Backward compat (internal / executor) ---
            if action == "save_strategy":
                return self._save_strategy(kwargs)
            if action == "log_strategy_execution":
                return self._log_strategy_execution(kwargs)

            return json.dumps({"error": f"Unknown action: {action}"})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    # ------------------------------------------------------------------
    # Compact output helper
    # ------------------------------------------------------------------

    @staticmethod
    def _compact(text: str) -> str:
        """Enforce max output size for LLM consumption."""
        if len(text) <= _MAX_OUTPUT_CHARS:
            return text
        return text[:_MAX_OUTPUT_CHARS - 20] + "\n[...truncated]"

    def _net_label(self) -> str:
        return "TESTNET" if self._testnet else "MAINNET"

    # ==================================================================
    # COMPOSITE ACTIONS (LLM-facing, compact text output)
    # ==================================================================

    # ---- status ------------------------------------------------------

    def _action_status(self) -> str:
        """Positions + account summary + open orders in one call."""
        self._rate_limiter.wait_if_needed(20)
        state = self._info.user_state(self._address)

        margin = state.get("marginSummary", {})
        # Auto-save snapshot
        self._store.save_snapshot(
            snapshot=state,
            total_pnl=float(margin.get("totalRawUsd", 0)) if margin else None,
            account_value=float(margin.get("accountValue", 0)) if margin else None,
            margin_used=float(margin.get("totalMarginUsed", 0)) if margin else None,
        )

        # Parse positions
        active_positions = []
        total_unrealized = 0.0
        for pos in state.get("assetPositions", []):
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
                    "liquidation_price": entry.get("liquidationPx"),
                })

        # Daily PnL
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        today_trades = self._store.get_trades(after=today_start)
        daily_realized = sum(t.get("pnl", 0) or 0 for t in today_trades)

        # Open orders
        self._rate_limiter.wait_if_needed(20)
        orders = self._info.open_orders(self._address)

        return self._compact(self._format_status(
            margin, active_positions, total_unrealized,
            daily_realized, orders, state.get("withdrawable"),
        ))

    def _format_status(
        self,
        margin: dict,
        positions: list[dict],
        total_unrealized: float,
        daily_realized: float,
        orders: list[dict],
        withdrawable: Any,
    ) -> str:
        acct_val = margin.get("accountValue", "?")
        margin_used = margin.get("totalMarginUsed", "?")
        daily_total = daily_realized + total_unrealized

        lines = [
            f"{self._net_label()} | Value: ${acct_val} | Margin used: ${margin_used} | Withdrawable: ${withdrawable}",
            f"Daily PnL: {_signed(daily_total)} (realized: {_signed(daily_realized)}, unrealized: {_signed(total_unrealized)})",
        ]

        # Positions
        lines.append(f"Positions ({len(positions)}):")
        if not positions:
            lines.append("  (none)")
        for p in positions:
            lines.append(self._format_position_line(p))

        # Orders
        lines.append(f"Open Orders ({len(orders)}):")
        if not orders:
            lines.append("  (none)")
        for o in orders[:10]:
            lines.append(self._format_order_line(o))
        if len(orders) > 10:
            lines.append(f"  ... and {len(orders) - 10} more")

        return "\n".join(lines)

    @staticmethod
    def _format_position_line(p: dict) -> str:
        coin = p.get("coin", "?")
        size = p.get("size", 0)
        direction = "long" if size > 0 else "short"
        entry = p.get("entry_price")
        pnl = p.get("unrealized_pnl", 0)
        liq = p.get("liquidation_price")
        lev = p.get("leverage")

        entry_f = f"${float(entry):,.2f}" if entry else "?"
        pnl_f = _signed(pnl)
        entry_val = abs(size) * float(entry) if entry else 0
        pnl_pct = f" ({pnl / entry_val * 100:+.1f}%)" if entry_val else ""
        liq_f = f", Liq: ${float(liq):,.0f}" if liq else ""
        lev_f = f", {lev}" if lev else ""
        return f"  {coin}: {abs(size)} {direction} @ {entry_f}, PnL: {pnl_f}{pnl_pct}{liq_f}{lev_f}"

    @staticmethod
    def _format_order_line(o: dict) -> str:
        coin = o.get("coin", "?")
        side = "buy" if o.get("side", "").lower() in ("b", "buy", "bid") else "sell"
        sz = o.get("sz", "?")
        px = o.get("limitPx", o.get("px", "?"))
        oid = o.get("oid", "")
        return f"  {coin} {side} {sz} @ ${px} (oid:{oid})"

    # ---- analyze -----------------------------------------------------

    def _action_analyze(self, kw: dict) -> str:
        """Price + indicators + funding for a coin."""
        coin = kw.get("coin")
        if not coin:
            return json.dumps({"error": "coin is required for analyze"})

        interval = kw.get("interval", "1h")
        lookback_hours = kw.get("lookback_hours", 48)

        # 1. Fetch candles (never returned raw)
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - lookback_hours * 3600 * 1000
        self._rate_limiter.wait_if_needed(20)
        candles = self._info.candles_snapshot(coin, interval, start_ms, now_ms)

        if not candles:
            return json.dumps({"error": f"No candle data for {coin}"})

        current_price = float(candles[-1]["c"])

        # 2. Compute default indicators
        indicators_cfg = kw.get("indicators") or [
            {"name": "rsi", "period": 14},
            {"name": "ema", "period": 20},
            {"name": "atr", "period": 14},
            {"name": "macd", "fast": 12, "slow": 26, "signal_period": 9},
        ]

        from src.indicators import compute_indicators
        raw = compute_indicators(candles, indicators_cfg, history_length=1)

        # Flatten to latest values
        compact_ind = {}
        for key, val in raw.items():
            if isinstance(val, dict):
                if "latest" in val:
                    compact_ind[key] = val["latest"]
                else:
                    compact_ind[key] = {
                        sk: sv.get("latest") if isinstance(sv, dict) else sv
                        for sk, sv in val.items()
                    }
            else:
                compact_ind[key] = val

        # 3. Fetch funding rate
        funding_str = ""
        try:
            self._rate_limiter.wait_if_needed(20)
            meta_ctx = self._info.meta_and_asset_ctxs()
            universe = meta_ctx[0]["universe"]
            asset_ctxs = meta_ctx[1]
            for i, asset_info in enumerate(universe):
                if asset_info["name"] == coin:
                    ctx = asset_ctxs[i]
                    funding = float(ctx.get("funding", "0"))
                    annualized = funding * 8760 * 100
                    oi = ctx.get("openInterest", "?")
                    funding_str = f"Funding: {funding * 100:.4f}% ({annualized:.1f}%/yr) | OI: {oi}"
                    break
        except Exception:
            funding_str = "Funding: unavailable"

        return self._compact(self._format_analysis(
            coin, interval, current_price, compact_ind, funding_str, len(candles),
        ))

    @staticmethod
    def _format_analysis(
        coin: str,
        interval: str,
        price: float,
        indicators: dict,
        funding_str: str,
        candle_count: int,
    ) -> str:
        lines = [
            f"{coin} ({interval}, {candle_count} candles)",
            f"Price: ${price:,.2f} | {funding_str}",
        ]

        # Format indicators compactly
        ind_parts = []
        for key, val in indicators.items():
            if isinstance(val, dict):
                # Multi-output (MACD, Bollinger, Stochastic)
                sub_parts = []
                for sk, sv in val.items():
                    if sv is not None:
                        sv_f = f"{sv:.2f}" if isinstance(sv, float) else str(sv)
                        sub_parts.append(f"{sk}={sv_f}")
                ind_parts.append(f"{key}: {', '.join(sub_parts)}")
            elif val is not None:
                val_f = f"{val:.2f}" if isinstance(val, float) else str(val)
                ind_parts.append(f"{key}={val_f}")

        lines.append("  ".join(ind_parts))
        return "\n".join(lines)

    # ---- trade -------------------------------------------------------

    def _action_trade(self, kw: dict) -> str:
        """Unified trading: open/close/limit_order/cancel."""
        sub = kw.get("sub_action")
        if not sub:
            return json.dumps({"error": "sub_action required: open|close|limit_order|cancel"})

        if sub == "open":
            return self._trade_open(kw)
        if sub == "close":
            return self._trade_close(kw)
        if sub == "limit_order":
            return self._trade_limit(kw)
        if sub == "cancel":
            return self._trade_cancel(kw)
        return json.dumps({"error": f"Unknown trade sub_action: {sub}"})

    def _trade_open(self, kw: dict) -> str:
        coin = kw.get("coin")
        is_buy = kw.get("is_buy")
        size = kw.get("size")
        slippage = kw.get("slippage", 0.01)

        if not all([coin, is_buy is not None, size]):
            return json.dumps({"error": "coin, is_buy, and size are required"})

        check = self._pre_trade_check(coin, size)
        if check:
            return json.dumps({"error": check})

        # Set leverage if requested
        leverage = kw.get("leverage")
        if leverage:
            if leverage > self._max_leverage:
                return json.dumps({"error": f"Leverage {leverage}x exceeds max {self._max_leverage}x"})
            self._rate_limiter.wait_if_needed(1)
            self._exchange.update_leverage(leverage, coin, kw.get("is_cross", True))

        self._rate_limiter.wait_if_needed(1)
        result = self._exchange.market_open(coin, is_buy, size, slippage)

        tp = kw.get("take_profit_price")
        sl = kw.get("stop_loss_price")
        self._store.log_trade(
            coin=coin, action="market_open",
            side="buy" if is_buy else "sell",
            size=size, order_type="market",
            metadata={"result": result, "slippage": slippage, "tp": tp, "sl": sl},
        )

        # Place TP/SL if specified
        tpsl_info = ""
        if tp or sl:
            exit_side = not is_buy
            orders = []
            if tp:
                orders.append({
                    "coin": coin, "is_buy": exit_side, "sz": size,
                    "limit_px": tp,
                    "order_type": {"trigger": {"triggerPx": str(tp), "isMarket": True, "tpsl": "tp"}},
                    "reduce_only": True,
                })
            if sl:
                orders.append({
                    "coin": coin, "is_buy": exit_side, "sz": size,
                    "limit_px": sl,
                    "order_type": {"trigger": {"triggerPx": str(sl), "isMarket": True, "tpsl": "sl"}},
                    "reduce_only": True,
                })
            self._rate_limiter.wait_if_needed(1)
            self._exchange.bulk_orders(orders, grouping="normalTpsl")
            tp_s = f", TP: ${tp}" if tp else ""
            sl_s = f", SL: ${sl}" if sl else ""
            tpsl_info = tp_s + sl_s

        side_str = "long" if is_buy else "short"
        lev_s = f", {leverage}x" if leverage else ""
        return f"Opened {coin} {side_str}: {size} @ market{lev_s}{tpsl_info}"

    def _trade_close(self, kw: dict) -> str:
        coin = kw.get("coin")
        slippage = kw.get("slippage", 0.01)
        if not coin:
            return json.dumps({"error": "coin is required"})

        self._rate_limiter.wait_if_needed(1)
        result = self._exchange.market_close(coin, slippage=slippage)

        self._store.log_trade(
            coin=coin, action="market_close", order_type="market",
            metadata={"result": result, "slippage": slippage},
        )
        return f"Closed {coin} position @ market"

    def _trade_limit(self, kw: dict) -> str:
        coin = kw.get("coin")
        is_buy = kw.get("is_buy")
        size = kw.get("size")
        price = kw.get("price")

        if not all([coin, is_buy is not None, size, price is not None]):
            return json.dumps({"error": "coin, is_buy, size, and price are required"})

        check = self._pre_trade_check(coin, size)
        if check:
            return json.dumps({"error": check})

        tp = kw.get("take_profit_price")
        sl = kw.get("stop_loss_price")

        if tp or sl:
            # Bulk order with TP/SL
            exit_side = not is_buy
            orders = [
                {
                    "coin": coin, "is_buy": is_buy, "sz": size,
                    "limit_px": price,
                    "order_type": {"limit": {"tif": "Gtc"}},
                    "reduce_only": False,
                },
            ]
            if tp:
                orders.append({
                    "coin": coin, "is_buy": exit_side, "sz": size,
                    "limit_px": tp,
                    "order_type": {"trigger": {"triggerPx": str(tp), "isMarket": True, "tpsl": "tp"}},
                    "reduce_only": True,
                })
            if sl:
                orders.append({
                    "coin": coin, "is_buy": exit_side, "sz": size,
                    "limit_px": sl,
                    "order_type": {"trigger": {"triggerPx": str(sl), "isMarket": True, "tpsl": "sl"}},
                    "reduce_only": True,
                })
            self._rate_limiter.wait_if_needed(1)
            result = self._exchange.bulk_orders(orders, grouping="normalTpsl")
            self._store.log_trade(
                coin=coin, action="order_placed_tpsl",
                side="buy" if is_buy else "sell",
                size=size, price=price, order_type="limit+tpsl",
                metadata={"result": result, "tp": tp, "sl": sl},
            )
        else:
            ot = {"limit": {"tif": "Gtc"}}
            self._rate_limiter.wait_if_needed(1)
            result = self._exchange.order(coin, is_buy, size, price, ot)
            self._store.log_trade(
                coin=coin, action="order_placed",
                side="buy" if is_buy else "sell",
                size=size, price=price, order_type="limit",
                metadata=result,
            )

        side_str = "buy" if is_buy else "sell"
        tp_s = f", TP: ${tp}" if tp else ""
        sl_s = f", SL: ${sl}" if sl else ""
        return f"Placed {coin} limit {side_str} {size} @ ${price}{tp_s}{sl_s}"

    def _trade_cancel(self, kw: dict) -> str:
        coin = kw.get("coin")
        order_id = kw.get("order_id")
        if not all([coin, order_id is not None]):
            return json.dumps({"error": "coin and order_id are required"})

        self._rate_limiter.wait_if_needed(1)
        self._exchange.cancel(coin, order_id)

        self._store.log_trade(
            coin=coin, action="order_cancelled",
            trade_id=str(order_id), metadata={},
        )
        return f"Cancelled order {order_id} on {coin}"

    # ---- history -----------------------------------------------------

    def _action_history(self, kw: dict) -> str:
        """Compact trade history."""
        coin = kw.get("coin")
        limit = kw.get("limit", 10)
        trades = self._store.get_trades(coin=coin, limit=limit)
        summary = self._store.get_trade_summary(coin=coin)

        lines = [f"Recent Trades ({len(trades)}" + (f" for {coin}" if coin else "") + "):"]
        for t in trades:
            ts = t.get("created_at", "?")
            if isinstance(ts, str) and len(ts) > 16:
                ts = ts[:16]
            c = t.get("coin", "?")
            act = t.get("action", "?")
            sz = t.get("size", "")
            px = t.get("price", "")
            pnl = t.get("pnl")
            pnl_s = f" PnL: {_signed(pnl)}" if pnl is not None else ""
            sz_s = f" {sz}" if sz else ""
            px_s = f" @ ${px}" if px else ""
            lines.append(f"  {ts} {c} {act}{sz_s}{px_s}{pnl_s}")

        if summary:
            total = summary.get("total_trades", 0)
            pnl = summary.get("total_pnl", 0)
            wins = summary.get("winning_trades", 0)
            losses = summary.get("losing_trades", 0)
            wr = f"{wins}/{total} ({wins / total * 100:.0f}%)" if total > 0 else "0/0"
            lines.append(f"Summary: {total} trades, PnL: {_signed(pnl)}, Win: {wr}")

        return self._compact("\n".join(lines))

    # ---- strategy ----------------------------------------------------

    def _action_strategy(self, kw: dict) -> str:
        """Unified strategy CRUD + performance."""
        sub = kw.get("sub_action")
        if not sub:
            return json.dumps({"error": "sub_action required: create|list|get|activate|deactivate|delete|performance"})

        if sub == "create":
            return self._create_strategy(kw)
        if sub == "list":
            return self._list_strategies()
        if sub == "get":
            return self._get_strategy(kw)
        if sub == "activate":
            return self._toggle_strategy(kw, active=True)
        if sub == "deactivate":
            return self._toggle_strategy(kw, active=False)
        if sub == "delete":
            return self._delete_strategy(kw)
        if sub == "performance":
            return self._strategy_performance(kw)
        return json.dumps({"error": f"Unknown strategy sub_action: {sub}"})

    # ==================================================================
    # INTERNAL METHODS (preserved for StrategyExecutor and composites)
    # ==================================================================

    # ---- helpers -----------------------------------------------------

    def _tag(self, data: dict) -> dict:
        """Add network tag to response."""
        data["network"] = "TESTNET" if self._testnet else "MAINNET"
        return data

    def _pre_trade_check(self, coin: str, size: float) -> str | None:
        """Validate trade against safety limits. Returns error string or None."""
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

        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        today_trades = self._store.get_trades(after=today_start)
        realized_pnl = sum(t.get("pnl", 0) or 0 for t in today_trades)

        unrealized_pnl = 0.0
        try:
            self._rate_limiter.wait_if_needed(20)
            state = self._info.user_state(self._address)
            for pos in state.get("assetPositions", []):
                entry = pos.get("position", {})
                unrealized_pnl += float(entry.get("unrealizedPnl", 0))
        except Exception:
            pass

        daily_pnl = realized_pnl + unrealized_pnl
        if daily_pnl < -self._max_loss_usd:
            return (
                f"Daily loss ${abs(daily_pnl):.0f} (realized: ${abs(realized_pnl):.0f}, "
                f"unrealized: ${abs(unrealized_pnl):.0f}) exceeds limit "
                f"${self._max_loss_usd:.0f}. Trading halted."
            )

        return None

    # ---- info (internal, used by composites) -------------------------

    def _get_positions(self) -> str:
        self._rate_limiter.wait_if_needed(20)
        state = self._info.user_state(self._address)
        margin = state.get("marginSummary", {})
        self._store.save_snapshot(
            snapshot=state,
            total_pnl=float(margin.get("totalRawUsd", 0)) if margin else None,
            account_value=float(margin.get("accountValue", 0)) if margin else None,
            margin_used=float(margin.get("totalMarginUsed", 0)) if margin else None,
        )
        active_positions = []
        for pos in state.get("assetPositions", []):
            entry = pos.get("position", {})
            szi = float(entry.get("szi", "0"))
            if szi != 0:
                active_positions.append({
                    "coin": entry.get("coin"),
                    "size": szi,
                    "entry_price": entry.get("entryPx"),
                    "unrealized_pnl": float(entry.get("unrealizedPnl", "0")),
                    "leverage": entry.get("leverage"),
                    "liquidation_price": entry.get("liquidationPx"),
                })
        return json.dumps(self._tag({
            "positions": active_positions,
            "position_count": len(active_positions),
            "account_value": margin.get("accountValue"),
            "total_margin_used": margin.get("totalMarginUsed"),
            "withdrawable": state.get("withdrawable"),
        }), ensure_ascii=False)

    def _get_open_orders(self) -> str:
        self._rate_limiter.wait_if_needed(20)
        orders = self._info.open_orders(self._address)
        return json.dumps(self._tag({"open_orders": orders, "count": len(orders)}), ensure_ascii=False)

    def _get_fills(self, kw: dict) -> str:
        self._rate_limiter.wait_if_needed(20)
        fills = self._info.user_fills(self._address)
        limit = kw.get("limit", 50)
        return json.dumps(self._tag({"fills": fills[:limit], "count": len(fills[:limit])}), ensure_ascii=False)

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
        if len(candles) > _MAX_CANDLES:
            candles = candles[-_MAX_CANDLES:]
        return json.dumps(
            self._tag({"coin": coin, "interval": interval, "candles": candles, "count": len(candles)}),
            ensure_ascii=False,
        )

    def _get_indicators(self, kw: dict) -> str:
        coin = kw.get("coin")
        if not coin:
            return json.dumps({"error": "coin is required for get_indicators"})
        indicators = kw.get("indicators")
        if not indicators:
            return json.dumps({"error": "indicators list is required for get_indicators"})
        interval = kw.get("interval", "1h")
        lookback_hours = kw.get("lookback_hours", 48)
        include_history = kw.get("include_history", False)
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - lookback_hours * 3600 * 1000
        self._rate_limiter.wait_if_needed(20)
        candles = self._info.candles_snapshot(coin, interval, start_ms, now_ms)
        if not candles:
            return json.dumps(self._tag({"error": f"No candle data for {coin}"}))
        from src.indicators import compute_indicators
        history_len = 10 if include_history else 1
        results = compute_indicators(candles, indicators, history_length=history_len)
        if not include_history:
            compact = {}
            for key, val in results.items():
                if isinstance(val, dict):
                    if "latest" in val:
                        compact[key] = val["latest"]
                    else:
                        compact[key] = {
                            sk: sv.get("latest") if isinstance(sv, dict) else sv
                            for sk, sv in val.items()
                        }
                else:
                    compact[key] = val
            results = compact
        current_price = float(candles[-1]["c"])
        return json.dumps(self._tag({
            "coin": coin, "interval": interval,
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
                annualized = funding * 8760 * 100
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

    # ---- trading (internal) ------------------------------------------

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
            coin=coin, action="market_close", order_type="market",
            metadata={"result": result, "slippage": slippage},
        )
        return json.dumps(self._tag({"market_close_result": result}), ensure_ascii=False)

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

    # ---- strategy (internal) -----------------------------------------

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
            strats = self._store.list_strategies()
            return json.dumps(self._tag({"strategies": strats, "count": len(strats)}), ensure_ascii=False)
        strat = self._store.get_strategy(name)
        if strat is None:
            return json.dumps(self._tag({"error": f"Strategy '{name}' not found"}))
        return json.dumps(self._tag({"strategy": strat}), ensure_ascii=False)

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

        direct_tool_call = {
            "tool": "hyperliquid",
            "args": {"action": "execute_strategy", "strategy_name": name},
        }

        scheduler_result = None
        if self._scheduler_store:
            try:
                task_id = self._scheduler_store.add(
                    name=scheduler_task_name,
                    prompt=prompt,
                    cron_expression=schedule,
                    deliver_to=deliver_to,
                    telegram_chat_id=telegram_chat_id,
                    direct_tool_call=direct_tool_call,
                )
                task = self._scheduler_store.get(scheduler_task_name)
                scheduler_result = {
                    "task_id": task_id,
                    "next_run_at": task.get("next_run_at") if task else None,
                }
            except Exception:
                scheduler_result = {"error": "Failed to register scheduler task"}

        coins_s = ", ".join(coins) if coins else "none"
        sched_s = ""
        if scheduler_result and "next_run_at" in scheduler_result:
            sched_s = f", next run: {scheduler_result['next_run_at']}"
        return f"Created strategy '{name}' (id:{sid}), coins: [{coins_s}], schedule: {schedule}{sched_s}"

    def _build_strategy_prompt(self, name: str, state: dict) -> str:
        return (
            f"Execute: hyperliquid(action='execute_strategy', strategy_name='{name}'). "
            f"Report the result."
        )

    def _toggle_strategy(self, kw: dict, active: bool) -> str:
        name = kw.get("strategy_name")
        if not name:
            return json.dumps({"error": "strategy_name is required"})

        strat = self._store.get_strategy(name)
        if not strat:
            return json.dumps({"error": f"Strategy '{name}' not found"})

        state = strat["state"]
        state["status"] = "active" if active else "inactive"
        self._store.save_strategy(name, state)

        scheduler_toggled = False
        task_name = state.get("scheduler_task_name")
        if task_name and self._scheduler_store:
            scheduler_toggled = self._scheduler_store.toggle(task_name, enabled=active)

        action_word = "Activated" if active else "Deactivated"
        return f"{action_word} strategy '{name}'" + (", scheduler updated" if scheduler_toggled else "")

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
        status = "deleted" if deleted else "not found"
        sched_s = ", scheduler task removed" if scheduler_deleted else ""
        return f"Strategy '{name}': {status}{sched_s}"

    def _list_strategies(self) -> str:
        strats = self._store.list_strategies()
        if not strats:
            return "No strategies configured."

        lines = [f"Strategies ({len(strats)}):"]
        for s in strats:
            full = self._store.get_strategy(s["name"])
            state = full["state"] if full else {}
            status = state.get("status", "?")
            coins_s = ",".join(state.get("coins", []))
            sched = state.get("schedule", "?")
            last = state.get("last_executed_at", "never")
            if last and isinstance(last, str) and len(last) > 16:
                last = last[:16]
            lines.append(f"  {s['name']}: {status}, [{coins_s}], {sched}, last: {last}")
        return "\n".join(lines)

    def _strategy_performance(self, kw: dict) -> str:
        name = kw.get("strategy_name")
        if not name:
            return json.dumps({"error": "strategy_name is required"})
        perf = self._store.get_strategy_performance(name)
        if not perf:
            return f"No performance data for strategy '{name}'."
        total = perf.get("trade_count", 0)
        pnl = perf.get("total_pnl", 0)
        wr = perf.get("win_rate", 0)
        avg_w = perf.get("avg_win", 0)
        avg_l = perf.get("avg_loss", 0)
        dd = perf.get("max_drawdown", 0)
        pf = perf.get("profit_factor", 0)
        return (
            f"Strategy '{name}' performance:\n"
            f"  Trades: {total}, PnL: {_signed(pnl)}, Win rate: {wr * 100:.0f}%\n"
            f"  Avg win: {_signed(avg_w)}, Avg loss: {_signed(avg_l)}\n"
            f"  Max drawdown: {_signed(-abs(dd))}, Profit factor: {pf:.2f}"
        )

    def _log_strategy_execution(self, kw: dict) -> str:
        name = kw.get("strategy_name")
        if not name:
            return json.dumps({"error": "strategy_name is required"})

        signals = kw.get("signals")
        actions = kw.get("actions_taken")
        notes = kw.get("notes")

        pnl_snapshot = kw.get("pnl_snapshot")
        if pnl_snapshot is None:
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

    # ---- deterministic strategy execution ----------------------------

    def _execute_strategy(self, kw: dict) -> str:
        name = kw.get("strategy_name")
        if not name:
            return json.dumps({"error": "strategy_name is required"})

        from src.strategy_executor import StrategyExecutor
        executor = StrategyExecutor(self)
        result = executor.execute(name)
        return json.dumps(self._tag(result), ensure_ascii=False)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _signed(value: Any) -> str:
    """Format a number with explicit sign."""
    if value is None:
        return "$0"
    v = float(value)
    if v >= 0:
        return f"+${v:,.2f}"
    return f"-${abs(v):,.2f}"
