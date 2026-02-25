"""Hyperliquid trade log and strategy state persistence."""

import json
from datetime import datetime, timezone
from typing import Any

from src.db import Database


class HyperliquidStore:
    """Persistent storage for Hyperliquid trading data.

    Four tables:
    - hl_trades: Append-only trade log (orders, fills, cancellations).
    - hl_position_snapshots: Periodic position state captures.
    - hl_strategy_state: Key-value store for strategy parameters.
    - hl_strategy_executions: Audit log of strategy execution events.
    """

    def __init__(self, db: Database) -> None:
        self._db = db
        self._init_schema()

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS hl_trades (
                        id SERIAL PRIMARY KEY,
                        trade_id TEXT,
                        coin TEXT NOT NULL,
                        action TEXT NOT NULL,
                        side TEXT,
                        size NUMERIC,
                        price NUMERIC,
                        order_type TEXT,
                        pnl NUMERIC,
                        metadata JSONB,
                        created_at TEXT NOT NULL
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS hl_position_snapshots (
                        id SERIAL PRIMARY KEY,
                        snapshot JSONB NOT NULL,
                        total_pnl NUMERIC,
                        account_value NUMERIC,
                        margin_used NUMERIC,
                        created_at TEXT NOT NULL
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS hl_strategy_state (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        state JSONB NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS hl_strategy_executions (
                        id SERIAL PRIMARY KEY,
                        strategy_name TEXT NOT NULL,
                        signals JSONB,
                        actions JSONB,
                        pnl_snapshot NUMERIC,
                        notes TEXT,
                        created_at TEXT NOT NULL
                    )
                """)
                # Migration: add strategy_name column to hl_trades if missing.
                cur.execute("""
                    DO $$ BEGIN
                        ALTER TABLE hl_trades ADD COLUMN strategy_name TEXT;
                    EXCEPTION
                        WHEN duplicate_column THEN NULL;
                    END $$
                """)
            conn.commit()
        finally:
            self._db.put_connection(conn)

    # ------------------------------------------------------------------
    # Trade log
    # ------------------------------------------------------------------

    def log_trade(
        self,
        coin: str,
        action: str,
        side: str | None = None,
        size: float | None = None,
        price: float | None = None,
        order_type: str | None = None,
        pnl: float | None = None,
        trade_id: str | None = None,
        metadata: dict | None = None,
        strategy_name: str | None = None,
    ) -> int:
        """Append a trade event to the log.

        Returns:
            The ID of the new trade record.
        """
        now = datetime.now(timezone.utc).isoformat()
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO hl_trades
                       (trade_id, coin, action, side, size, price,
                        order_type, pnl, metadata, created_at, strategy_name)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING id""",
                    (trade_id, coin, action, side, size, price,
                     order_type, pnl,
                     json.dumps(metadata) if metadata else None,
                     now, strategy_name),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"]
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.put_connection(conn)

    def get_trades(
        self,
        coin: str | None = None,
        action: str | None = None,
        limit: int = 50,
        after: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Query trade log with optional filters.

        Args:
            coin: Filter by trading pair.
            action: Filter by action type.
            limit: Max results (default: 50).
            after: Only trades after this timestamp.
        """
        conditions = []
        params: list[Any] = []

        if coin:
            conditions.append("coin = %s")
            params.append(coin)
        if action:
            conditions.append("action = %s")
            params.append(action)
        if after:
            conditions.append("created_at >= %s")
            params.append(after.isoformat())

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = (
            f"SELECT id, trade_id, coin, action, side, size, price, "
            f"order_type, pnl, metadata, created_at "
            f"FROM hl_trades {where} ORDER BY id DESC LIMIT %s"
        )
        params.append(limit)

        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._db.put_connection(conn)

    def get_trade_summary(self, coin: str | None = None) -> dict[str, Any]:
        """Aggregate trade statistics.

        Returns:
            Dict with total_trades, total_pnl, winning_trades, losing_trades.
        """
        condition = "WHERE coin = %s" if coin else ""
        params: list[Any] = [coin] if coin else []

        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT COUNT(*) AS total_trades, "
                    f"COALESCE(SUM(pnl), 0) AS total_pnl, "
                    f"COUNT(CASE WHEN pnl > 0 THEN 1 END) AS winning_trades, "
                    f"COUNT(CASE WHEN pnl < 0 THEN 1 END) AS losing_trades "
                    f"FROM hl_trades {condition}",
                    params,
                )
                row = cur.fetchone()
            return dict(row)
        finally:
            self._db.put_connection(conn)

    # ------------------------------------------------------------------
    # Position snapshots
    # ------------------------------------------------------------------

    def save_snapshot(
        self,
        snapshot: dict,
        total_pnl: float | None = None,
        account_value: float | None = None,
        margin_used: float | None = None,
    ) -> int:
        """Save a position snapshot.

        Returns:
            The ID of the new snapshot.
        """
        now = datetime.now(timezone.utc).isoformat()
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO hl_position_snapshots
                       (snapshot, total_pnl, account_value, margin_used, created_at)
                       VALUES (%s, %s, %s, %s, %s)
                       RETURNING id""",
                    (json.dumps(snapshot), total_pnl, account_value, margin_used, now),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"]
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.put_connection(conn)

    def get_snapshots(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent position snapshots."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, snapshot, total_pnl, account_value, margin_used, "
                    "created_at FROM hl_position_snapshots "
                    "ORDER BY id DESC LIMIT %s",
                    (limit,),
                )
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._db.put_connection(conn)

    # ------------------------------------------------------------------
    # Strategy state
    # ------------------------------------------------------------------

    def save_strategy(self, name: str, state: dict) -> int:
        """Upsert a strategy state.

        Returns:
            The ID of the strategy record.
        """
        now = datetime.now(timezone.utc).isoformat()
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO hl_strategy_state (name, state, updated_at)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (name) DO UPDATE
                       SET state = EXCLUDED.state, updated_at = EXCLUDED.updated_at
                       RETURNING id""",
                    (name, json.dumps(state), now),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"]
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.put_connection(conn)

    def get_strategy(self, name: str) -> dict[str, Any] | None:
        """Load a strategy by name.

        Returns None if not found.
        """
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, state, updated_at "
                    "FROM hl_strategy_state WHERE name = %s",
                    (name,),
                )
                row = cur.fetchone()
            return dict(row) if row else None
        finally:
            self._db.put_connection(conn)

    def list_strategies(self) -> list[dict[str, Any]]:
        """List all strategy names and timestamps."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, updated_at "
                    "FROM hl_strategy_state ORDER BY name"
                )
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._db.put_connection(conn)

    def delete_strategy(self, name: str) -> bool:
        """Remove a strategy by name.

        Returns:
            True if a strategy was removed, False if not found.
        """
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM hl_strategy_state WHERE name = %s", (name,),
                )
                removed = cur.rowcount > 0
            conn.commit()
            return removed
        finally:
            self._db.put_connection(conn)

    # ------------------------------------------------------------------
    # Strategy execution log
    # ------------------------------------------------------------------

    def log_execution(
        self,
        strategy_name: str,
        signals: dict | None = None,
        actions: dict | None = None,
        pnl_snapshot: float | None = None,
        notes: str | None = None,
    ) -> int:
        """Log a strategy execution event.

        Returns:
            The ID of the execution record.
        """
        now = datetime.now(timezone.utc).isoformat()
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO hl_strategy_executions
                       (strategy_name, signals, actions, pnl_snapshot, notes, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       RETURNING id""",
                    (
                        strategy_name,
                        json.dumps(signals) if signals else None,
                        json.dumps(actions) if actions else None,
                        pnl_snapshot,
                        notes,
                        now,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"]
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.put_connection(conn)

    def get_executions(
        self,
        strategy_name: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get recent execution records for a strategy."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, strategy_name, signals, actions, pnl_snapshot, "
                    "notes, created_at FROM hl_strategy_executions "
                    "WHERE strategy_name = %s ORDER BY id DESC LIMIT %s",
                    (strategy_name, limit),
                )
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._db.put_connection(conn)

    def get_strategy_trades(
        self,
        strategy_name: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get trades linked to a strategy."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, trade_id, coin, action, side, size, price, "
                    "order_type, pnl, metadata, created_at, strategy_name "
                    "FROM hl_trades WHERE strategy_name = %s "
                    "ORDER BY id DESC LIMIT %s",
                    (strategy_name, limit),
                )
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._db.put_connection(conn)

    def get_strategy_performance(
        self,
        strategy_name: str,
    ) -> dict[str, Any]:
        """Compute performance metrics for a strategy from its trade log.

        Returns:
            Dict with total_pnl, trade_count, win_count, loss_count,
            win_rate, avg_win, avg_loss, max_drawdown, profit_factor.
        """
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pnl FROM hl_trades "
                    "WHERE strategy_name = %s AND pnl IS NOT NULL "
                    "ORDER BY id ASC",
                    (strategy_name,),
                )
                rows = cur.fetchall()
        finally:
            self._db.put_connection(conn)

        pnls = [float(r["pnl"]) for r in rows]
        if not pnls:
            return {
                "trade_count": 0, "total_pnl": 0.0,
                "win_count": 0, "loss_count": 0, "win_rate": 0.0,
                "avg_win": 0.0, "avg_loss": 0.0,
                "max_drawdown": 0.0, "profit_factor": 0.0,
            }

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        total_pnl = sum(pnls)

        # Max drawdown from cumulative PnL curve
        cum = 0.0
        peak = 0.0
        max_dd = 0.0
        for p in pnls:
            cum += p
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd

        gross_wins = sum(wins) if wins else 0.0
        gross_losses = abs(sum(losses)) if losses else 0.0

        return {
            "trade_count": len(pnls),
            "total_pnl": round(total_pnl, 2),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": round(len(wins) / len(pnls), 4) if pnls else 0.0,
            "avg_win": round(gross_wins / len(wins), 2) if wins else 0.0,
            "avg_loss": round(gross_losses / len(losses), 2) if losses else 0.0,
            "max_drawdown": round(max_dd, 2),
            "profit_factor": round(gross_wins / gross_losses, 4) if gross_losses > 0 else float("inf"),
        }
