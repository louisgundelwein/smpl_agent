"""Tests for src.hyperliquid_store — Trade log and strategy persistence (cursor-mocked)."""

import json
from unittest.mock import MagicMock

import pytest

from src.hyperliquid_store import HyperliquidStore


def _make_store():
    """Create a HyperliquidStore with a mock Database."""
    db = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()

    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    db.get_connection.return_value = conn

    cursor.execute.return_value = None
    store = HyperliquidStore(db=db)
    return store, db, conn, cursor


# ------------------------------------------------------------------
# Trade log
# ------------------------------------------------------------------


def test_log_trade():
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = {"id": 42}
    tid = store.log_trade(
        coin="ETH", action="order_placed", side="buy",
        size=1.5, price=3000.0, order_type="limit",
        trade_id="oid-1", metadata={"leverage": 10},
    )
    assert tid == 42
    conn.commit.assert_called()


def test_log_trade_minimal():
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = {"id": 1}
    tid = store.log_trade(coin="BTC", action="fill")
    assert tid == 1


def test_get_trades_no_filters():
    store, db, conn, cursor = _make_store()
    cursor.fetchall.return_value = [
        {"id": 1, "trade_id": "t1", "coin": "ETH", "action": "fill",
         "side": "buy", "size": 1, "price": 3000, "order_type": "market",
         "pnl": None, "metadata": None, "created_at": "2025-01-01T00:00:00+00:00"},
    ]
    trades = store.get_trades()
    assert len(trades) == 1
    assert trades[0]["coin"] == "ETH"


def test_get_trades_with_coin_filter():
    store, db, conn, cursor = _make_store()
    cursor.fetchall.return_value = []
    trades = store.get_trades(coin="SOL", limit=10)
    assert trades == []
    # Verify SQL contains coin filter
    call_args = cursor.execute.call_args
    assert "coin = %s" in call_args[0][0]


def test_get_trades_with_after_filter():
    store, db, conn, cursor = _make_store()
    cursor.fetchall.return_value = []
    from datetime import datetime, timezone
    after = datetime(2025, 6, 1, tzinfo=timezone.utc)
    trades = store.get_trades(after=after)
    assert trades == []
    call_args = cursor.execute.call_args
    assert "created_at >= %s" in call_args[0][0]


def test_get_trade_summary():
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = {
        "total_trades": 10,
        "total_pnl": 500.0,
        "winning_trades": 7,
        "losing_trades": 3,
    }
    summary = store.get_trade_summary()
    assert summary["total_trades"] == 10
    assert summary["total_pnl"] == 500.0
    assert summary["winning_trades"] == 7


def test_get_trade_summary_with_coin():
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = {
        "total_trades": 5, "total_pnl": 100.0,
        "winning_trades": 3, "losing_trades": 2,
    }
    summary = store.get_trade_summary(coin="BTC")
    call_args = cursor.execute.call_args
    assert "WHERE coin = %s" in call_args[0][0]


# ------------------------------------------------------------------
# Position snapshots
# ------------------------------------------------------------------


def test_save_snapshot():
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = {"id": 7}
    sid = store.save_snapshot(
        snapshot={"positions": []},
        total_pnl=123.45,
        account_value=10000.0,
        margin_used=500.0,
    )
    assert sid == 7
    conn.commit.assert_called()


def test_get_snapshots():
    store, db, conn, cursor = _make_store()
    cursor.fetchall.return_value = [
        {"id": 1, "snapshot": {}, "total_pnl": 0,
         "account_value": 1000, "margin_used": 0,
         "created_at": "2025-01-01T00:00:00+00:00"},
    ]
    snaps = store.get_snapshots(limit=5)
    assert len(snaps) == 1


# ------------------------------------------------------------------
# Strategy state
# ------------------------------------------------------------------


def test_save_strategy():
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = {"id": 3}
    sid = store.save_strategy("eth-swing", {"entry_rsi": 30, "exit_rsi": 70})
    assert sid == 3
    conn.commit.assert_called()


def test_save_strategy_upsert():
    """save_strategy uses INSERT ... ON CONFLICT ... DO UPDATE."""
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = {"id": 3}
    store.save_strategy("eth-swing", {"entry_rsi": 25})
    call_args = cursor.execute.call_args
    assert "ON CONFLICT" in call_args[0][0]


def test_get_strategy_found():
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = {
        "id": 3, "name": "eth-swing",
        "state": {"entry_rsi": 30}, "updated_at": "2025-01-01T00:00:00+00:00",
    }
    strat = store.get_strategy("eth-swing")
    assert strat is not None
    assert strat["name"] == "eth-swing"


def test_get_strategy_not_found():
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = None
    assert store.get_strategy("nope") is None


def test_list_strategies():
    store, db, conn, cursor = _make_store()
    cursor.fetchall.return_value = [
        {"id": 1, "name": "a", "updated_at": "t1"},
        {"id": 2, "name": "b", "updated_at": "t2"},
    ]
    strats = store.list_strategies()
    assert len(strats) == 2
    assert strats[0]["name"] == "a"


def test_delete_strategy():
    store, db, conn, cursor = _make_store()
    cursor.rowcount = 1
    assert store.delete_strategy("old") is True
    conn.commit.assert_called()


def test_delete_strategy_not_found():
    store, db, conn, cursor = _make_store()
    cursor.rowcount = 0
    assert store.delete_strategy("ghost") is False


# ------------------------------------------------------------------
# Trade log — strategy_name support
# ------------------------------------------------------------------


def test_log_trade_with_strategy_name():
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = {"id": 50}
    tid = store.log_trade(
        coin="ETH", action="market_open", strategy_name="eth-rsi",
    )
    assert tid == 50
    call_args = cursor.execute.call_args
    assert "strategy_name" in call_args[0][0]


# ------------------------------------------------------------------
# Strategy execution log
# ------------------------------------------------------------------


def test_log_execution():
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = {"id": 10}
    eid = store.log_execution(
        strategy_name="eth-rsi",
        signals={"rsi": 28.5},
        actions={"action": "buy", "size": 0.1},
        pnl_snapshot=150.0,
        notes="RSI below 30, entering long",
    )
    assert eid == 10
    conn.commit.assert_called()


def test_log_execution_minimal():
    store, db, conn, cursor = _make_store()
    cursor.fetchone.return_value = {"id": 11}
    eid = store.log_execution(strategy_name="btc-momentum")
    assert eid == 11


def test_get_executions():
    store, db, conn, cursor = _make_store()
    cursor.fetchall.return_value = [
        {"id": 1, "strategy_name": "eth-rsi", "signals": {},
         "actions": {}, "pnl_snapshot": 100, "notes": "",
         "created_at": "2025-01-01T00:00:00+00:00"},
    ]
    execs = store.get_executions("eth-rsi", limit=10)
    assert len(execs) == 1
    call_args = cursor.execute.call_args
    assert "strategy_name = %s" in call_args[0][0]


def test_get_strategy_trades():
    store, db, conn, cursor = _make_store()
    cursor.fetchall.return_value = [
        {"id": 1, "trade_id": "t1", "coin": "ETH", "action": "market_open",
         "side": "buy", "size": 1, "price": 3000, "order_type": "market",
         "pnl": None, "metadata": None,
         "created_at": "2025-01-01T00:00:00+00:00", "strategy_name": "eth-rsi"},
    ]
    trades = store.get_strategy_trades("eth-rsi")
    assert len(trades) == 1
    call_args = cursor.execute.call_args
    assert "strategy_name = %s" in call_args[0][0]


def test_get_strategy_performance():
    store, db, conn, cursor = _make_store()
    cursor.fetchall.return_value = [
        {"pnl": 100.0},
        {"pnl": -50.0},
        {"pnl": 200.0},
        {"pnl": -30.0},
    ]
    perf = store.get_strategy_performance("eth-rsi")
    assert perf["trade_count"] == 4
    assert perf["total_pnl"] == 220.0
    assert perf["win_count"] == 2
    assert perf["loss_count"] == 2
    assert perf["win_rate"] == 0.5
    assert perf["avg_win"] == 150.0   # (100+200)/2
    assert perf["avg_loss"] == 40.0   # (50+30)/2
    assert perf["max_drawdown"] == 50.0  # peak at 100, dip to 50
    assert perf["profit_factor"] == pytest.approx(300.0 / 80.0, abs=0.01)


def test_get_strategy_performance_empty():
    store, db, conn, cursor = _make_store()
    cursor.fetchall.return_value = []
    perf = store.get_strategy_performance("nonexistent")
    assert perf["trade_count"] == 0
    assert perf["total_pnl"] == 0.0
