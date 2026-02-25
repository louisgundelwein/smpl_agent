"""Tests for src.tools.hyperliquid — Hyperliquid trading tool (SDK fully mocked)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.hyperliquid_store import HyperliquidStore
from src.tools.hyperliquid import HyperliquidTool


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


# ------------------------------------------------------------------
# Info actions
# ------------------------------------------------------------------


class TestGetPositions:
    def test_returns_user_state(self, tool, mock_info, store):
        mock_info.user_state.return_value = {
            "assetPositions": [],
            "marginSummary": {"accountValue": "10000", "totalRawUsd": "0", "totalMarginUsed": "0"},
        }
        result = _parse(tool.execute(action="get_positions"))
        assert "positions" in result
        assert result["network"] == "TESTNET"
        mock_info.user_state.assert_called_once()


class TestGetOpenOrders:
    def test_returns_orders(self, tool, mock_info):
        mock_info.open_orders.return_value = [{"oid": 1, "coin": "ETH"}]
        result = _parse(tool.execute(action="get_open_orders"))
        assert result["count"] == 1
        assert result["open_orders"][0]["coin"] == "ETH"


class TestGetFills:
    def test_returns_fills(self, tool, mock_info):
        mock_info.user_fills.return_value = [
            {"coin": "BTC", "sz": "1", "px": "50000", "closedPnl": "100"},
        ]
        result = _parse(tool.execute(action="get_fills"))
        assert result["count"] == 1

    def test_respects_limit(self, tool, mock_info):
        mock_info.user_fills.return_value = [{"i": i} for i in range(100)]
        result = _parse(tool.execute(action="get_fills", limit=5))
        assert result["count"] == 5


# ------------------------------------------------------------------
# Market data actions
# ------------------------------------------------------------------


class TestGetPrice:
    def test_single_coin(self, tool, mock_info):
        mock_info.all_mids.return_value = {"ETH": "3000.5", "BTC": "50000"}
        result = _parse(tool.execute(action="get_price", coin="ETH"))
        assert result["mid_price"] == "3000.5"
        assert result["coin"] == "ETH"

    def test_all_prices(self, tool, mock_info):
        mock_info.all_mids.return_value = {"ETH": "3000", "BTC": "50000"}
        result = _parse(tool.execute(action="get_price"))
        assert "prices" in result
        assert len(result["prices"]) == 2

    def test_unknown_coin(self, tool, mock_info):
        mock_info.all_mids.return_value = {"ETH": "3000"}
        result = _parse(tool.execute(action="get_price", coin="FAKECOIN"))
        assert "error" in result


class TestGetOrderbook:
    def test_returns_book(self, tool, mock_info):
        mock_info.l2_snapshot.return_value = {
            "levels": [
                [{"px": "3000", "sz": "10", "n": 3}],
                [{"px": "3001", "sz": "5", "n": 2}],
            ]
        }
        result = _parse(tool.execute(action="get_orderbook", coin="ETH"))
        assert result["coin"] == "ETH"
        assert "orderbook" in result

    def test_missing_coin(self, tool):
        result = _parse(tool.execute(action="get_orderbook"))
        assert "error" in result


class TestGetCandles:
    def test_returns_candles(self, tool, mock_info):
        mock_info.candles_snapshot.return_value = [
            {"t": 1000, "o": "3000", "h": "3050", "l": "2980", "c": "3020", "v": "100"},
        ]
        result = _parse(tool.execute(action="get_candles", coin="ETH", interval="1h"))
        assert result["count"] == 1
        assert result["interval"] == "1h"

    def test_truncates_large_result(self, tool, mock_info):
        mock_info.candles_snapshot.return_value = [{"i": i} for i in range(500)]
        result = _parse(tool.execute(action="get_candles", coin="ETH"))
        assert result["count"] == 200  # _MAX_CANDLES

    def test_missing_coin(self, tool):
        result = _parse(tool.execute(action="get_candles"))
        assert "error" in result


# ------------------------------------------------------------------
# Trading actions
# ------------------------------------------------------------------


class TestPlaceOrder:
    def test_places_limit_order(self, tool, mock_info, mock_exchange):
        mock_info.all_mids.return_value = {"ETH": "3000"}
        mock_exchange.order.return_value = {"status": "ok", "response": {"type": "order"}}
        result = _parse(tool.execute(
            action="place_order", coin="ETH", is_buy=True,
            size=1.0, price=3000.0, order_type="limit",
        ))
        assert "order_result" in result
        mock_exchange.order.assert_called_once()

    def test_places_market_order(self, tool, mock_info, mock_exchange):
        mock_info.all_mids.return_value = {"ETH": "3000"}
        mock_exchange.order.return_value = {"status": "ok"}
        result = _parse(tool.execute(
            action="place_order", coin="ETH", is_buy=False,
            size=0.5, price=3000.0, order_type="market",
        ))
        assert "order_result" in result
        # Market order uses IoC
        call_args = mock_exchange.order.call_args
        assert call_args[0][4] == {"limit": {"tif": "Ioc"}}

    def test_missing_params(self, tool):
        result = _parse(tool.execute(action="place_order", coin="ETH"))
        assert "error" in result


class TestPlaceOrderWithTpsl:
    def test_places_with_tp_and_sl(self, tool, mock_info, mock_exchange):
        mock_info.all_mids.return_value = {"ETH": "3000"}
        mock_exchange.bulk_orders.return_value = {"status": "ok"}
        result = _parse(tool.execute(
            action="place_order_with_tpsl", coin="ETH", is_buy=True,
            size=1.0, price=3000.0,
            take_profit_price=3500.0, stop_loss_price=2800.0,
        ))
        assert "order_result" in result
        # Should have 3 orders: entry + TP + SL
        call_args = mock_exchange.bulk_orders.call_args
        assert len(call_args[0][0]) == 3
        assert call_args[1]["grouping"] == "normalTpsl"

    def test_tp_only(self, tool, mock_info, mock_exchange):
        mock_info.all_mids.return_value = {"ETH": "3000"}
        mock_exchange.bulk_orders.return_value = {"status": "ok"}
        result = _parse(tool.execute(
            action="place_order_with_tpsl", coin="ETH", is_buy=True,
            size=1.0, price=3000.0, take_profit_price=3500.0,
        ))
        assert "order_result" in result
        call_args = mock_exchange.bulk_orders.call_args
        assert len(call_args[0][0]) == 2  # entry + TP

    def test_missing_both_tpsl(self, tool, mock_info):
        mock_info.all_mids.return_value = {"ETH": "3000"}
        result = _parse(tool.execute(
            action="place_order_with_tpsl", coin="ETH", is_buy=True,
            size=1.0, price=3000.0,
        ))
        assert "error" in result


class TestMarketOpen:
    def test_opens_position(self, tool, mock_info, mock_exchange):
        mock_info.all_mids.return_value = {"ETH": "3000"}
        mock_exchange.market_open.return_value = {"status": "ok"}
        result = _parse(tool.execute(
            action="market_open", coin="ETH", is_buy=True, size=2.0,
        ))
        assert "market_open_result" in result
        mock_exchange.market_open.assert_called_once_with("ETH", True, 2.0, 0.01)

    def test_custom_slippage(self, tool, mock_info, mock_exchange):
        mock_info.all_mids.return_value = {"ETH": "3000"}
        mock_exchange.market_open.return_value = {"status": "ok"}
        tool.execute(action="market_open", coin="ETH", is_buy=True, size=1.0, slippage=0.05)
        mock_exchange.market_open.assert_called_once_with("ETH", True, 1.0, 0.05)

    def test_missing_params(self, tool):
        result = _parse(tool.execute(action="market_open", coin="ETH"))
        assert "error" in result


class TestMarketClose:
    def test_closes_position(self, tool, mock_exchange):
        mock_exchange.market_close.return_value = {"status": "ok"}
        result = _parse(tool.execute(action="market_close", coin="ETH"))
        assert "market_close_result" in result
        mock_exchange.market_close.assert_called_once()

    def test_missing_coin(self, tool):
        result = _parse(tool.execute(action="market_close"))
        assert "error" in result


class TestCancelOrder:
    def test_cancels(self, tool, mock_exchange):
        mock_exchange.cancel.return_value = {"status": "ok"}
        result = _parse(tool.execute(
            action="cancel_order", coin="ETH", order_id=12345,
        ))
        assert "cancel_result" in result
        mock_exchange.cancel.assert_called_once_with("ETH", 12345)

    def test_missing_params(self, tool):
        result = _parse(tool.execute(action="cancel_order", coin="ETH"))
        assert "error" in result


# ------------------------------------------------------------------
# Config actions
# ------------------------------------------------------------------


class TestSetLeverage:
    def test_sets_leverage(self, tool, mock_exchange):
        mock_exchange.update_leverage.return_value = {"status": "ok"}
        result = _parse(tool.execute(
            action="set_leverage", coin="ETH", leverage=10,
        ))
        assert result["leverage"] == 10
        mock_exchange.update_leverage.assert_called_once_with(10, "ETH", True)

    def test_exceeds_max(self, tool):
        result = _parse(tool.execute(
            action="set_leverage", coin="ETH", leverage=50,
        ))
        assert "error" in result
        assert "50x exceeds max" in result["error"]

    def test_isolated_margin(self, tool, mock_exchange):
        mock_exchange.update_leverage.return_value = {"status": "ok"}
        tool.execute(action="set_leverage", coin="ETH", leverage=5, is_cross=False)
        mock_exchange.update_leverage.assert_called_once_with(5, "ETH", False)


# ------------------------------------------------------------------
# Safety checks
# ------------------------------------------------------------------


class TestSafetyChecks:
    def test_position_size_exceeded(self, tool, mock_info):
        mock_info.all_mids.return_value = {"ETH": "5000"}
        # 3 ETH * $5000 = $15000 > max $10000
        result = _parse(tool.execute(
            action="place_order", coin="ETH", is_buy=True,
            size=3.0, price=5000.0,
        ))
        assert "error" in result
        assert "exceeds limit" in result["error"]

    def test_daily_loss_exceeded(self, tool, mock_info, store):
        mock_info.all_mids.return_value = {"ETH": "3000"}
        # Mock store to return trades with large losses
        store.get_trades = MagicMock(return_value=[
            {"pnl": -600}, {"pnl": -500},
        ])
        result = _parse(tool.execute(
            action="place_order", coin="ETH", is_buy=True,
            size=0.1, price=3000.0,
        ))
        assert "error" in result
        assert "Trading halted" in result["error"]

    def test_unknown_coin_in_pre_check(self, tool, mock_info):
        mock_info.all_mids.return_value = {"ETH": "3000"}
        result = _parse(tool.execute(
            action="place_order", coin="FAKECOIN", is_buy=True,
            size=1.0, price=100.0,
        ))
        assert "error" in result
        assert "Cannot determine price" in result["error"]


# ------------------------------------------------------------------
# Strategy / history actions
# ------------------------------------------------------------------


class TestGetTradeHistory:
    def test_returns_trades_and_summary(self, tool, store):
        store.get_trades = MagicMock(return_value=[{"id": 1, "coin": "ETH"}])
        store.get_trade_summary = MagicMock(return_value={
            "total_trades": 1, "total_pnl": 50.0,
            "winning_trades": 1, "losing_trades": 0,
        })
        result = _parse(tool.execute(action="get_trade_history"))
        assert len(result["trades"]) == 1
        assert result["summary"]["total_pnl"] == 50.0


class TestSaveStrategy:
    def test_saves(self, tool, store):
        store.save_strategy = MagicMock(return_value=5)
        result = _parse(tool.execute(
            action="save_strategy",
            strategy_name="eth-swing",
            strategy_state={"entry_rsi": 30},
        ))
        assert result["saved"] is True
        assert result["name"] == "eth-swing"
        store.save_strategy.assert_called_once_with("eth-swing", {"entry_rsi": 30})

    def test_missing_params(self, tool):
        result = _parse(tool.execute(action="save_strategy"))
        assert "error" in result


class TestGetStrategy:
    def test_found(self, tool, store):
        store.get_strategy = MagicMock(return_value={
            "id": 5, "name": "eth-swing",
            "state": {"entry_rsi": 30}, "updated_at": "t",
        })
        result = _parse(tool.execute(
            action="get_strategy", strategy_name="eth-swing",
        ))
        assert result["strategy"]["name"] == "eth-swing"

    def test_not_found(self, tool, store):
        store.get_strategy = MagicMock(return_value=None)
        result = _parse(tool.execute(
            action="get_strategy", strategy_name="nope",
        ))
        assert "error" in result

    def test_list_all(self, tool, store):
        store.list_strategies = MagicMock(return_value=[
            {"id": 1, "name": "a", "updated_at": "t"},
        ])
        result = _parse(tool.execute(action="get_strategy"))
        assert result["count"] == 1


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
        result = _parse(tool.execute(action="get_positions"))
        assert "error" in result
        assert "API timeout" in result["error"]

    def test_network_tag_present(self, tool, mock_info):
        mock_info.all_mids.return_value = {"ETH": "3000"}
        result = _parse(tool.execute(action="get_price", coin="ETH"))
        assert result["network"] == "TESTNET"


# ------------------------------------------------------------------
# Extended market data actions
# ------------------------------------------------------------------


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


class TestGetIndicators:
    def test_returns_computed_indicators(self, tool, mock_info):
        mock_info.candles_snapshot.return_value = _sample_candles(50)
        result = _parse(tool.execute(
            action="get_indicators",
            coin="ETH",
            indicators=[{"name": "rsi", "period": 14}],
        ))
        assert "indicators" in result
        assert result["current_price"] is not None
        assert result["coin"] == "ETH"
        assert result["network"] == "TESTNET"

    def test_multiple_indicators(self, tool, mock_info):
        mock_info.candles_snapshot.return_value = _sample_candles(50)
        result = _parse(tool.execute(
            action="get_indicators",
            coin="ETH",
            indicators=[
                {"name": "rsi", "period": 14},
                {"name": "ema", "period": 20},
                {"name": "bollinger_bands", "period": 20},
            ],
        ))
        assert "rsi_14" in result["indicators"]
        assert "ema_20" in result["indicators"]

    def test_missing_coin(self, tool):
        result = _parse(tool.execute(
            action="get_indicators",
            indicators=[{"name": "rsi"}],
        ))
        assert "error" in result

    def test_missing_indicators(self, tool):
        result = _parse(tool.execute(action="get_indicators", coin="ETH"))
        assert "error" in result

    def test_no_candle_data(self, tool, mock_info):
        mock_info.candles_snapshot.return_value = []
        result = _parse(tool.execute(
            action="get_indicators",
            coin="ETH",
            indicators=[{"name": "rsi"}],
        ))
        assert "error" in result


class TestGetFundingRate:
    def test_returns_funding(self, tool, mock_info):
        mock_info.meta_and_asset_ctxs.return_value = [
            {"universe": [{"name": "ETH", "szDecimals": 3}]},
            [{"funding": "0.0001", "premium": "0.00005",
              "markPx": "3000", "oraclePx": "2999",
              "openInterest": "50000"}],
        ]
        result = _parse(tool.execute(action="get_funding_rate", coin="ETH"))
        assert result["coin"] == "ETH"
        assert "current_funding_rate" in result
        assert "annualized_rate_pct" in result
        assert result["network"] == "TESTNET"

    def test_unknown_coin(self, tool, mock_info):
        mock_info.meta_and_asset_ctxs.return_value = [
            {"universe": [{"name": "BTC", "szDecimals": 5}]},
            [{"funding": "0.0001"}],
        ]
        result = _parse(tool.execute(action="get_funding_rate", coin="FAKE"))
        assert "error" in result

    def test_missing_coin(self, tool):
        result = _parse(tool.execute(action="get_funding_rate"))
        assert "error" in result


class TestGetAccountSummary:
    def test_returns_summary(self, tool, mock_info, store):
        mock_info.user_state.return_value = {
            "assetPositions": [{
                "position": {
                    "coin": "ETH",
                    "szi": "1.5",
                    "entryPx": "3000",
                    "unrealizedPnl": "150",
                    "leverage": {"type": "cross", "value": 10},
                },
            }],
            "marginSummary": {
                "accountValue": "15000",
                "totalMarginUsed": "5000",
                "totalRawUsd": "200",
            },
            "withdrawable": "10000",
        }
        store.get_trades = MagicMock(return_value=[])
        result = _parse(tool.execute(action="get_account_summary"))
        assert result["account_value"] == "15000"
        assert result["position_count"] == 1
        assert result["total_unrealized_pnl"] == 150.0
        assert result["network"] == "TESTNET"

    def test_no_positions(self, tool, mock_info, store):
        mock_info.user_state.return_value = {
            "assetPositions": [{
                "position": {"coin": "ETH", "szi": "0", "unrealizedPnl": "0"},
            }],
            "marginSummary": {
                "accountValue": "10000",
                "totalMarginUsed": "0",
                "totalRawUsd": "0",
            },
            "withdrawable": "10000",
        }
        store.get_trades = MagicMock(return_value=[])
        result = _parse(tool.execute(action="get_account_summary"))
        assert result["position_count"] == 0


# ------------------------------------------------------------------
# Strategy lifecycle actions
# ------------------------------------------------------------------


class TestCreateStrategy:
    def test_creates_with_scheduler(self, tool, store):
        sched_store = MagicMock()
        sched_store.add.return_value = 5
        sched_store.get.return_value = {"next_run_at": "2026-01-01T00:05:00+00:00"}
        tool._scheduler_store = sched_store

        store.save_strategy = MagicMock(return_value=10)
        result = _parse(tool.execute(
            action="create_strategy",
            strategy_name="eth-rsi",
            description="RSI mean reversion",
            coins=["ETH"],
            schedule="every 5m",
            parameters={"entry_rsi": 30, "exit_rsi": 70},
        ))
        assert result["created"] is True
        assert result["name"] == "eth-rsi"
        assert result["strategy_id"] == 10
        assert result["scheduler_task"] is not None
        store.save_strategy.assert_called_once()
        sched_store.add.assert_called_once()

    def test_creates_without_scheduler(self, tool, store):
        tool._scheduler_store = None
        store.save_strategy = MagicMock(return_value=10)
        result = _parse(tool.execute(
            action="create_strategy",
            strategy_name="eth-rsi",
            schedule="every 5m",
        ))
        assert result["created"] is True
        assert result["scheduler_task"] is None

    def test_missing_name(self, tool):
        result = _parse(tool.execute(action="create_strategy", schedule="every 5m"))
        assert "error" in result

    def test_missing_schedule(self, tool):
        result = _parse(tool.execute(
            action="create_strategy", strategy_name="test",
        ))
        assert "error" in result

    def test_invalid_schedule(self, tool, store):
        store.save_strategy = MagicMock(return_value=1)
        result = _parse(tool.execute(
            action="create_strategy",
            strategy_name="test",
            schedule="invalid cron garbage",
        ))
        assert "error" in result
        assert "Invalid schedule" in result["error"]


class TestToggleStrategy:
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

        result = _parse(tool.execute(
            action="activate_strategy", strategy_name="eth-rsi",
        ))
        assert result.get("activated") is True
        assert result["status"] == "active"
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

        result = _parse(tool.execute(
            action="deactivate_strategy", strategy_name="eth-rsi",
        ))
        assert result.get("deactivated") is True
        assert result["status"] == "inactive"

    def test_strategy_not_found(self, tool, store):
        store.get_strategy = MagicMock(return_value=None)
        result = _parse(tool.execute(
            action="activate_strategy", strategy_name="nope",
        ))
        assert "error" in result

    def test_missing_name(self, tool):
        result = _parse(tool.execute(action="activate_strategy"))
        assert "error" in result


class TestDeleteStrategy:
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

        result = _parse(tool.execute(
            action="delete_strategy", strategy_name="eth-rsi",
        ))
        assert result["deleted"] is True
        assert result["scheduler_deleted"] is True

    def test_deletes_without_scheduler(self, tool, store):
        store.get_strategy = MagicMock(return_value={
            "id": 1, "name": "eth-rsi",
            "state": {},
            "updated_at": "t",
        })
        store.delete_strategy = MagicMock(return_value=True)
        tool._scheduler_store = None

        result = _parse(tool.execute(
            action="delete_strategy", strategy_name="eth-rsi",
        ))
        assert result["deleted"] is True
        assert result["scheduler_deleted"] is False

    def test_missing_name(self, tool):
        result = _parse(tool.execute(action="delete_strategy"))
        assert "error" in result


class TestListStrategies:
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
        result = _parse(tool.execute(action="list_strategies"))
        assert result["count"] == 1
        assert result["strategies"][0]["status"] == "active"
        assert result["strategies"][0]["coins"] == ["ETH"]

    def test_empty_list(self, tool, store):
        store.list_strategies = MagicMock(return_value=[])
        result = _parse(tool.execute(action="list_strategies"))
        assert result["count"] == 0


# ------------------------------------------------------------------
# Strategy performance and execution logging
# ------------------------------------------------------------------


class TestStrategyPerformance:
    def test_returns_perf(self, tool, store):
        store.get_strategy_performance = MagicMock(return_value={
            "total_pnl": 500.0, "trade_count": 10,
            "win_count": 7, "loss_count": 3,
            "win_rate": 0.7, "avg_win": 100.0, "avg_loss": 50.0,
            "max_drawdown": 200.0, "profit_factor": 4.67,
        })
        result = _parse(tool.execute(
            action="strategy_performance", strategy_name="eth-rsi",
        ))
        assert result["performance"]["win_rate"] == 0.7
        assert result["strategy_name"] == "eth-rsi"
        assert result["network"] == "TESTNET"

    def test_missing_name(self, tool):
        result = _parse(tool.execute(action="strategy_performance"))
        assert "error" in result


class TestLogStrategyExecution:
    def test_logs_execution(self, tool, mock_info, store):
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
            actions_taken={"action": "buy", "size": 0.1},
            notes="RSI below threshold",
        ))
        assert result["logged"] is True
        assert result["execution_id"] == 7
        store.log_execution.assert_called_once()

    def test_missing_name(self, tool):
        result = _parse(tool.execute(action="log_strategy_execution"))
        assert "error" in result

    def test_handles_pnl_fetch_failure(self, tool, mock_info, store):
        mock_info.user_state.side_effect = Exception("API error")
        store.log_execution = MagicMock(return_value=8)
        store.get_strategy = MagicMock(return_value={
            "id": 1, "name": "test",
            "state": {}, "updated_at": "t",
        })
        store.save_strategy = MagicMock(return_value=1)

        result = _parse(tool.execute(
            action="log_strategy_execution",
            strategy_name="test",
        ))
        assert result["logged"] is True
        # pnl_snapshot should be None since fetch failed
        call_args = store.log_execution.call_args
        assert call_args[1]["pnl_snapshot"] is None


class TestStrategyExecutionLog:
    def test_returns_executions(self, tool, store):
        store.get_executions = MagicMock(return_value=[
            {"id": 1, "strategy_name": "eth-rsi", "signals": {},
             "actions": {}, "pnl_snapshot": 100, "notes": "",
             "created_at": "2025-01-01T00:00:00+00:00"},
        ])
        result = _parse(tool.execute(
            action="strategy_execution_log", strategy_name="eth-rsi",
        ))
        assert result["count"] == 1
        assert result["strategy_name"] == "eth-rsi"

    def test_missing_name(self, tool):
        result = _parse(tool.execute(action="strategy_execution_log"))
        assert "error" in result

    def test_custom_limit(self, tool, store):
        store.get_executions = MagicMock(return_value=[])
        tool.execute(
            action="strategy_execution_log", strategy_name="test", limit=5,
        )
        store.get_executions.assert_called_once_with("test", limit=5)
