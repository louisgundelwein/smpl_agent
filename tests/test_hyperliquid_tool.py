"""Tests for src.tools.hyperliquid — Hyperliquid trading tool (SDK fully mocked).

Tests cover the refactored composite actions (status, analyze, trade,
history, strategy) as well as backward-compat paths (execute_strategy,
save_strategy, log_strategy_execution).
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.hyperliquid_store import HyperliquidStore
from src.tools.hyperliquid import HyperliquidTool, _MAX_OUTPUT_CHARS


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _make_store():
    """Create a HyperliquidStore with a mock Database."""
    db = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    db.get_connection.return_value = conn
    cursor.execute.return_value = None
    cursor.fetchone.return_value = {"id": 1}
    cursor.fetchall.return_value = []
    return HyperliquidStore(db=db)


@pytest.fixture()
def mock_info():
    return MagicMock()


@pytest.fixture()
def mock_exchange():
    return MagicMock()


@pytest.fixture()
def store():
    return _make_store()


@pytest.fixture()
def tool(store, mock_info, mock_exchange):
    with patch("src.tools.hyperliquid.Info", return_value=mock_info), \
         patch("src.tools.hyperliquid.Exchange", return_value=mock_exchange), \
         patch("src.tools.hyperliquid.Account"):
        t = HyperliquidTool(
            store=store,
            wallet_key="0x" + "ab" * 32,
            wallet_address="0x" + "cd" * 20,
            testnet=True,
            max_position_size_usd=10000,
            max_loss_usd=1000,
            max_leverage=20,
        )
    # Replace SDK clients with our mocks
    t._info = mock_info
    t._exchange = mock_exchange
    return t


def _parse(result: str) -> dict:
    """Parse tool JSON output."""
    return json.loads(result)


def _sample_candles(n: int = 50) -> list[dict]:
    """Generate sample candle data in Hyperliquid SDK format."""
    return [
        {
            "t": i * 3600000,
            "T": (i + 1) * 3600000,
            "o": str(100 + i),
            "h": str(101 + i),
            "l": str(99 + i),
            "c": str(100 + i),
            "v": "1000",
            "i": "1h",
            "s": "ETH",
            "n": 10,
        }
        for i in range(n)
    ]


def _mock_user_state(positions=None, account_value="10000", margin_used="3000", withdrawable="7000"):
    """Build a mock user_state response."""
    asset_positions = []
    for p in (positions or []):
        asset_positions.append({
            "position": {
                "coin": p["coin"],
                "szi": str(p["size"]),
                "entryPx": str(p.get("entry_price", 3000)),
                "unrealizedPnl": str(p.get("pnl", 0)),
                "leverage": p.get("leverage", {"type": "cross", "value": 10}),
                "liquidationPx": str(p.get("liq", 2400)),
            },
        })
    return {
        "assetPositions": asset_positions,
        "marginSummary": {
            "accountValue": account_value,
            "totalMarginUsed": margin_used,
            "totalRawUsd": "200",
        },
        "withdrawable": withdrawable,
    }


# ------------------------------------------------------------------
# Schema
# ------------------------------------------------------------------


class TestSchema:
    def test_schema_has_reduced_actions(self, tool):
        schema = tool.schema
        actions = schema["function"]["parameters"]["properties"]["action"]["enum"]
        assert set(actions) == {
            "status", "analyze", "trade", "history",
            "strategy", "execute_strategy",
        }

    def test_schema_is_compact(self, tool):
        """Schema should be significantly smaller than old 24-action version."""
        schema_str = json.dumps(tool.schema)
        # Old schema was ~2000+ chars; new should be under 1200
        assert len(schema_str) < 1500

    def test_schema_has_sub_action(self, tool):
        props = tool.schema["function"]["parameters"]["properties"]
        assert "sub_action" in props


# ------------------------------------------------------------------
# status action
# ------------------------------------------------------------------


class TestStatus:
    def test_returns_compact_text(self, tool, mock_info, store):
        mock_info.user_state.return_value = _mock_user_state(
            positions=[{"coin": "ETH", "size": 1.5, "entry_price": 3000, "pnl": 150}],
        )
        mock_info.open_orders.return_value = [{"coin": "ETH", "side": "B", "sz": "0.5", "limitPx": "2800", "oid": 123}]
        store.get_trades = MagicMock(return_value=[])

        result = tool.execute(action="status")

        # Should be plain text, not JSON
        assert not result.startswith("{")
        assert "TESTNET" in result
        assert "ETH" in result
        assert "1.5 long" in result
        assert "Positions (1)" in result
        assert "Open Orders (1)" in result

    def test_no_positions(self, tool, mock_info, store):
        mock_info.user_state.return_value = _mock_user_state()
        mock_info.open_orders.return_value = []
        store.get_trades = MagicMock(return_value=[])

        result = tool.execute(action="status")
        assert "Positions (0)" in result
        assert "(none)" in result

    def test_output_under_limit(self, tool, mock_info, store):
        """Even with many positions, output stays under _MAX_OUTPUT_CHARS."""
        positions = [
            {"coin": f"COIN{i}", "size": i * 0.1, "entry_price": 1000 + i, "pnl": i}
            for i in range(20)
        ]
        mock_info.user_state.return_value = _mock_user_state(positions=positions)
        mock_info.open_orders.return_value = [{"coin": f"C{i}", "side": "B", "sz": "1", "limitPx": "100", "oid": i} for i in range(15)]
        store.get_trades = MagicMock(return_value=[])

        result = tool.execute(action="status")
        assert len(result) <= _MAX_OUTPUT_CHARS


# ------------------------------------------------------------------
# analyze action
# ------------------------------------------------------------------


class TestAnalyze:
    def test_returns_compact_text(self, tool, mock_info):
        mock_info.candles_snapshot.return_value = _sample_candles(50)
        mock_info.meta_and_asset_ctxs.return_value = [
            {"universe": [{"name": "ETH"}]},
            [{"funding": "0.0001", "openInterest": "50000"}],
        ]

        result = tool.execute(action="analyze", coin="ETH")

        assert not result.startswith("{")
        assert "ETH" in result
        assert "Price:" in result
        assert "rsi" in result.lower() or "RSI" in result

    def test_missing_coin(self, tool):
        result = _parse(tool.execute(action="analyze"))
        assert "error" in result

    def test_no_candle_data(self, tool, mock_info):
        mock_info.candles_snapshot.return_value = []
        result = _parse(tool.execute(action="analyze", coin="ETH"))
        assert "error" in result

    def test_no_raw_candles_in_output(self, tool, mock_info):
        """Output must never contain raw candle OHLCV data."""
        mock_info.candles_snapshot.return_value = _sample_candles(200)
        mock_info.meta_and_asset_ctxs.return_value = [
            {"universe": [{"name": "ETH"}]},
            [{"funding": "0.0001", "openInterest": "50000"}],
        ]

        result = tool.execute(action="analyze", coin="ETH")
        # Should not contain candle arrays or OHLCV keys
        assert '"o":' not in result
        assert '"h":' not in result
        assert '"candles"' not in result

    def test_funding_fetch_failure_graceful(self, tool, mock_info):
        mock_info.candles_snapshot.return_value = _sample_candles(50)
        mock_info.meta_and_asset_ctxs.side_effect = Exception("API error")

        result = tool.execute(action="analyze", coin="ETH")
        assert "unavailable" in result
        # Should still return analysis without funding
        assert "Price:" in result


# ------------------------------------------------------------------
# trade action
# ------------------------------------------------------------------


class TestTradeOpen:
    def test_opens_market_position(self, tool, mock_info, mock_exchange):
        mock_info.all_mids.return_value = {"ETH": "3000"}
        mock_exchange.market_open.return_value = {"status": "ok"}

        result = tool.execute(action="trade", sub_action="open", coin="ETH", is_buy=True, size=2.0)

        assert "Opened ETH long" in result
        assert "2.0" in result
        mock_exchange.market_open.assert_called_once_with("ETH", True, 2.0, 0.01)

    def test_opens_with_leverage_and_tpsl(self, tool, mock_info, mock_exchange):
        mock_info.all_mids.return_value = {"ETH": "3000"}
        mock_exchange.market_open.return_value = {"status": "ok"}
        mock_exchange.bulk_orders.return_value = {"status": "ok"}

        result = tool.execute(
            action="trade", sub_action="open", coin="ETH",
            is_buy=True, size=1.0, leverage=10,
            take_profit_price=3500.0, stop_loss_price=2800.0,
        )

        assert "10x" in result
        assert "TP: $3500" in result
        assert "SL: $2800" in result
        mock_exchange.update_leverage.assert_called_once()
        mock_exchange.bulk_orders.assert_called_once()

    def test_missing_params(self, tool):
        result = _parse(tool.execute(action="trade", sub_action="open", coin="ETH"))
        assert "error" in result

    def test_exceeds_max_leverage(self, tool, mock_info):
        mock_info.all_mids.return_value = {"ETH": "3000"}
        result = _parse(tool.execute(
            action="trade", sub_action="open", coin="ETH",
            is_buy=True, size=1.0, leverage=50,
        ))
        assert "error" in result
        assert "exceeds max" in result["error"]


class TestTradeClose:
    def test_closes_position(self, tool, mock_exchange):
        mock_exchange.market_close.return_value = {"status": "ok"}
        result = tool.execute(action="trade", sub_action="close", coin="ETH")
        assert "Closed ETH" in result
        mock_exchange.market_close.assert_called_once()

    def test_missing_coin(self, tool):
        result = _parse(tool.execute(action="trade", sub_action="close"))
        assert "error" in result


class TestTradeLimitOrder:
    def test_places_limit_order(self, tool, mock_info, mock_exchange):
        mock_info.all_mids.return_value = {"ETH": "3000"}
        mock_exchange.order.return_value = {"status": "ok"}

        result = tool.execute(
            action="trade", sub_action="limit_order",
            coin="ETH", is_buy=True, size=1.0, price=2900.0,
        )

        assert "Placed ETH limit buy" in result
        assert "2900" in result
        mock_exchange.order.assert_called_once()

    def test_places_with_tpsl(self, tool, mock_info, mock_exchange):
        mock_info.all_mids.return_value = {"ETH": "3000"}
        mock_exchange.bulk_orders.return_value = {"status": "ok"}

        result = tool.execute(
            action="trade", sub_action="limit_order",
            coin="ETH", is_buy=True, size=1.0, price=2900.0,
            take_profit_price=3500.0, stop_loss_price=2800.0,
        )

        assert "Placed ETH limit buy" in result
        # Should use bulk_orders for TPSL
        call_args = mock_exchange.bulk_orders.call_args
        assert len(call_args[0][0]) == 3  # entry + TP + SL
        assert call_args[1]["grouping"] == "normalTpsl"

    def test_missing_params(self, tool):
        result = _parse(tool.execute(action="trade", sub_action="limit_order", coin="ETH"))
        assert "error" in result


class TestTradeCancel:
    def test_cancels_order(self, tool, mock_exchange):
        mock_exchange.cancel.return_value = {"status": "ok"}
        result = tool.execute(action="trade", sub_action="cancel", coin="ETH", order_id=12345)
        assert "Cancelled order 12345" in result
        mock_exchange.cancel.assert_called_once_with("ETH", 12345)

    def test_missing_params(self, tool):
        result = _parse(tool.execute(action="trade", sub_action="cancel", coin="ETH"))
        assert "error" in result


class TestTradeSubAction:
    def test_missing_sub_action(self, tool):
        result = _parse(tool.execute(action="trade"))
        assert "error" in result
        assert "sub_action" in result["error"]

    def test_unknown_sub_action(self, tool):
        result = _parse(tool.execute(action="trade", sub_action="foo"))
        assert "error" in result


# ------------------------------------------------------------------
# history action
# ------------------------------------------------------------------


class TestHistory:
    def test_returns_compact_text(self, tool, store):
        store.get_trades = MagicMock(return_value=[
            {"created_at": "2026-02-25T10:00:00", "coin": "ETH", "action": "buy", "size": 1.0, "price": 3000, "pnl": 50},
        ])
        store.get_trade_summary = MagicMock(return_value={
            "total_trades": 10, "total_pnl": 500.0,
            "winning_trades": 7, "losing_trades": 3,
        })

        result = tool.execute(action="history")

        assert not result.startswith("{")
        assert "Recent Trades" in result
        assert "ETH" in result
        assert "Summary:" in result
        assert "7/10" in result

    def test_default_limit_is_10(self, tool, store):
        store.get_trades = MagicMock(return_value=[])
        store.get_trade_summary = MagicMock(return_value={})

        tool.execute(action="history")
        store.get_trades.assert_called_once_with(coin=None, limit=10)

    def test_custom_limit(self, tool, store):
        store.get_trades = MagicMock(return_value=[])
        store.get_trade_summary = MagicMock(return_value={})

        tool.execute(action="history", limit=5, coin="BTC")
        store.get_trades.assert_called_once_with(coin="BTC", limit=5)


# ------------------------------------------------------------------
# strategy action
# ------------------------------------------------------------------


class TestStrategyCreate:
    def test_creates_with_scheduler(self, tool, store):
        sched_store = MagicMock()
        sched_store.add.return_value = 5
        sched_store.get.return_value = {"next_run_at": "2026-01-01T00:05:00+00:00"}
        tool._scheduler_store = sched_store

        store.save_strategy = MagicMock(return_value=10)
        result = tool.execute(
            action="strategy", sub_action="create",
            strategy_name="eth-rsi",
            coins=["ETH"],
            schedule="every 5m",
            parameters={"entry_rsi": 30},
        )

        assert "Created strategy 'eth-rsi'" in result
        assert "id:10" in result
        store.save_strategy.assert_called_once()
        sched_store.add.assert_called_once()

    def test_creates_without_scheduler(self, tool, store):
        tool._scheduler_store = None
        store.save_strategy = MagicMock(return_value=10)
        result = tool.execute(
            action="strategy", sub_action="create",
            strategy_name="eth-rsi",
            schedule="every 5m",
        )
        assert "Created strategy" in result

    def test_missing_name(self, tool):
        result = _parse(tool.execute(action="strategy", sub_action="create", schedule="every 5m"))
        assert "error" in result

    def test_missing_schedule(self, tool):
        result = _parse(tool.execute(action="strategy", sub_action="create", strategy_name="test"))
        assert "error" in result

    def test_invalid_schedule(self, tool, store):
        store.save_strategy = MagicMock(return_value=1)
        result = _parse(tool.execute(
            action="strategy", sub_action="create",
            strategy_name="test",
            schedule="invalid cron garbage",
        ))
        assert "error" in result
        assert "Invalid schedule" in result["error"]


class TestStrategyList:
    def test_enriched_listing(self, tool, store):
        store.list_strategies = MagicMock(return_value=[
            {"id": 1, "name": "eth-rsi", "updated_at": "t"},
        ])
        store.get_strategy = MagicMock(return_value={
            "id": 1, "name": "eth-rsi",
            "state": {
                "description": "RSI strategy",
                "status": "active",
                "coins": ["ETH"],
                "schedule": "every 5m",
                "last_executed_at": None,
            },
            "updated_at": "t",
        })
        result = tool.execute(action="strategy", sub_action="list")
        assert "eth-rsi" in result
        assert "active" in result
        assert "ETH" in result

    def test_empty_list(self, tool, store):
        store.list_strategies = MagicMock(return_value=[])
        result = tool.execute(action="strategy", sub_action="list")
        assert "No strategies" in result


class TestStrategyGet:
    def test_found(self, tool, store):
        store.get_strategy = MagicMock(return_value={
            "id": 5, "name": "eth-swing",
            "state": {"entry_rsi": 30}, "updated_at": "t",
        })
        result = _parse(tool.execute(
            action="strategy", sub_action="get", strategy_name="eth-swing",
        ))
        assert result["strategy"]["name"] == "eth-swing"

    def test_not_found(self, tool, store):
        store.get_strategy = MagicMock(return_value=None)
        result = _parse(tool.execute(
            action="strategy", sub_action="get", strategy_name="nope",
        ))
        assert "error" in result


class TestStrategyToggle:
    def test_activate(self, tool, store):
        store.get_strategy = MagicMock(return_value={
            "id": 1, "name": "eth-rsi",
            "state": {"status": "inactive", "scheduler_task_name": "strategy-eth-rsi"},
            "updated_at": "t",
        })
        store.save_strategy = MagicMock(return_value=1)
        sched_store = MagicMock()
        sched_store.toggle.return_value = True
        tool._scheduler_store = sched_store

        result = tool.execute(action="strategy", sub_action="activate", strategy_name="eth-rsi")
        assert "Activated" in result
        sched_store.toggle.assert_called_once_with("strategy-eth-rsi", enabled=True)

    def test_deactivate(self, tool, store):
        store.get_strategy = MagicMock(return_value={
            "id": 1, "name": "eth-rsi",
            "state": {"status": "active", "scheduler_task_name": "strategy-eth-rsi"},
            "updated_at": "t",
        })
        store.save_strategy = MagicMock(return_value=1)
        sched_store = MagicMock()
        sched_store.toggle.return_value = True
        tool._scheduler_store = sched_store

        result = tool.execute(action="strategy", sub_action="deactivate", strategy_name="eth-rsi")
        assert "Deactivated" in result

    def test_not_found(self, tool, store):
        store.get_strategy = MagicMock(return_value=None)
        result = _parse(tool.execute(
            action="strategy", sub_action="activate", strategy_name="nope",
        ))
        assert "error" in result

    def test_missing_name(self, tool):
        result = _parse(tool.execute(action="strategy", sub_action="activate"))
        assert "error" in result


class TestStrategyDelete:
    def test_deletes_with_scheduler(self, tool, store):
        store.get_strategy = MagicMock(return_value={
            "id": 1, "name": "eth-rsi",
            "state": {"scheduler_task_name": "strategy-eth-rsi"},
            "updated_at": "t",
        })
        store.delete_strategy = MagicMock(return_value=True)
        sched_store = MagicMock()
        sched_store.delete.return_value = True
        tool._scheduler_store = sched_store

        result = tool.execute(action="strategy", sub_action="delete", strategy_name="eth-rsi")
        assert "deleted" in result
        assert "scheduler task removed" in result

    def test_missing_name(self, tool):
        result = _parse(tool.execute(action="strategy", sub_action="delete"))
        assert "error" in result


class TestStrategyPerformance:
    def test_returns_compact_text(self, tool, store):
        store.get_strategy_performance = MagicMock(return_value={
            "total_pnl": 500.0, "trade_count": 10,
            "win_count": 7, "loss_count": 3,
            "win_rate": 0.7, "avg_win": 100.0, "avg_loss": 50.0,
            "max_drawdown": 200.0, "profit_factor": 4.67,
        })
        result = tool.execute(action="strategy", sub_action="performance", strategy_name="eth-rsi")
        assert "eth-rsi" in result
        assert "70%" in result
        assert "4.67" in result

    def test_missing_name(self, tool):
        result = _parse(tool.execute(action="strategy", sub_action="performance"))
        assert "error" in result

    def test_no_data(self, tool, store):
        store.get_strategy_performance = MagicMock(return_value=None)
        result = tool.execute(action="strategy", sub_action="performance", strategy_name="test")
        assert "No performance data" in result


class TestStrategySubAction:
    def test_missing_sub_action(self, tool):
        result = _parse(tool.execute(action="strategy"))
        assert "error" in result
        assert "sub_action" in result["error"]


# ------------------------------------------------------------------
# Safety checks (unchanged logic, new dispatch path)
# ------------------------------------------------------------------


class TestSafetyChecks:
    def test_position_size_exceeded(self, tool, mock_info):
        mock_info.all_mids.return_value = {"ETH": "5000"}
        result = _parse(tool.execute(
            action="trade", sub_action="open",
            coin="ETH", is_buy=True, size=3.0,
        ))
        assert "error" in result
        assert "exceeds limit" in result["error"]

    def test_daily_loss_exceeded(self, tool, mock_info, store):
        mock_info.all_mids.return_value = {"ETH": "3000"}
        store.get_trades = MagicMock(return_value=[
            {"pnl": -600}, {"pnl": -500},
        ])
        result = _parse(tool.execute(
            action="trade", sub_action="open",
            coin="ETH", is_buy=True, size=0.1,
        ))
        assert "error" in result
        assert "Trading halted" in result["error"]

    def test_unknown_coin(self, tool, mock_info):
        mock_info.all_mids.return_value = {"ETH": "3000"}
        result = _parse(tool.execute(
            action="trade", sub_action="open",
            coin="FAKECOIN", is_buy=True, size=1.0,
        ))
        assert "error" in result
        assert "Cannot determine price" in result["error"]


# ------------------------------------------------------------------
# Backward compatibility (preserved internal actions)
# ------------------------------------------------------------------


class TestBackwardCompat:
    def test_execute_strategy_still_works(self, tool, store):
        """execute_strategy action must still work for scheduler direct_tool_call."""
        store.get_strategy = MagicMock(return_value={
            "id": 1, "name": "test",
            "state": {"status": "inactive"},  # inactive → should skip
            "updated_at": "t",
        })

        result = _parse(tool.execute(action="execute_strategy", strategy_name="test"))
        assert result.get("status") == "skipped"

    def test_save_strategy_still_works(self, tool, store):
        store.save_strategy = MagicMock(return_value=5)
        result = _parse(tool.execute(
            action="save_strategy",
            strategy_name="eth-swing",
            strategy_state={"entry_rsi": 30},
        ))
        assert result["saved"] is True
        assert result["name"] == "eth-swing"
        store.save_strategy.assert_called_once_with("eth-swing", {"entry_rsi": 30})

    def test_log_strategy_execution_still_works(self, tool, mock_info, store):
        mock_info.user_state.return_value = {
            "marginSummary": {"totalRawUsd": "500"},
        }
        store.log_execution = MagicMock(return_value=7)
        store.get_strategy = MagicMock(return_value={
            "id": 1, "name": "eth-rsi",
            "state": {"last_executed_at": None},
            "updated_at": "t",
        })
        store.save_strategy = MagicMock(return_value=1)

        result = _parse(tool.execute(
            action="log_strategy_execution",
            strategy_name="eth-rsi",
            signals={"rsi": 28.5},
        ))
        assert result["logged"] is True
        assert result["execution_id"] == 7

    def test_log_handles_pnl_fetch_failure(self, tool, mock_info, store):
        mock_info.user_state.side_effect = Exception("API error")
        store.log_execution = MagicMock(return_value=8)
        store.get_strategy = MagicMock(return_value={
            "id": 1, "name": "test",
            "state": {}, "updated_at": "t",
        })
        store.save_strategy = MagicMock(return_value=1)

        result = _parse(tool.execute(
            action="log_strategy_execution", strategy_name="test",
        ))
        assert result["logged"] is True
        call_args = store.log_execution.call_args
        assert call_args[1]["pnl_snapshot"] is None


# ------------------------------------------------------------------
# Error handling
# ------------------------------------------------------------------


class TestErrorHandling:
    def test_unknown_action(self, tool):
        result = _parse(tool.execute(action="nonexistent"))
        assert "error" in result
        assert "Unknown action" in result["error"]

    def test_sdk_exception_caught(self, tool, mock_info):
        mock_info.user_state.side_effect = Exception("API timeout")
        result = _parse(tool.execute(action="status"))
        assert "error" in result
        assert "API timeout" in result["error"]


# ------------------------------------------------------------------
# Output size enforcement
# ------------------------------------------------------------------


class TestOutputSize:
    def test_compact_truncates_long_output(self, tool):
        long_text = "x" * (_MAX_OUTPUT_CHARS + 500)
        result = tool._compact(long_text)
        assert len(result) <= _MAX_OUTPUT_CHARS
        assert "[...truncated]" in result

    def test_compact_preserves_short_output(self, tool):
        short_text = "hello world"
        result = tool._compact(short_text)
        assert result == short_text
