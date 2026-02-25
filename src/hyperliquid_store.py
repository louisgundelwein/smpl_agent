"""Hyperliquid trade log and strategy state persistence."""

import json
from datetime import datetime, timezone
from typing import Any

from src.db import Database


class HyperliquidStore:
    """Persistent storage for Hyperliquid trading data.

    Three tables:
    - hl_trades: Append-only trade log (orders, fills, cancellations).
    - hl_position_snapshots: Periodic position state captures.
    - hl_strategy_state: Key-value store for strategy parameters.
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
                        order_type, pnl, metadata, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING id""",
                    (trade_id, coin, action, side, size, price,
                     order_type, pnl,
                     json.dumps(metadata) if metadata else None,
                     now),
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
