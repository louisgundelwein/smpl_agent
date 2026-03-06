"""Postgres connection pool via psycopg2."""

import logging
import psycopg2
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger(__name__)


class Database:
    """Thread-safe Postgres connection pool.

    Each store retrieves a connection via get_connection() and returns it
    via put_connection() when done. Connections use RealDictCursor by default.
    Includes health checks to validate connections before returning them.
    """

    def __init__(
        self,
        database_url: str,
        minconn: int = 1,
        maxconn: int = 10,
        connection_timeout: float = 5.0,
    ) -> None:
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn,
            maxconn,
            database_url,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        self._database_url = database_url
        self._connection_timeout = connection_timeout

    def get_connection(self, timeout: float | None = None):
        """Get a connection from the pool with health check.

        Args:
            timeout: Maximum seconds to wait for a connection (uses default if None).

        Returns:
            A validated database connection.

        Raises:
            psycopg2.pool.PoolError: If no connection available within timeout.
        """
        if timeout is None:
            timeout = self._connection_timeout

        try:
            conn = self._pool.getconn()
        except psycopg2.pool.PoolError:
            raise

        # Health check: verify connection is still valid
        if not self._is_healthy(conn):
            logger.warning("Stale connection detected, creating new one")
            try:
                conn.close()
            except Exception:
                pass
            # Create a new connection directly
            try:
                conn = psycopg2.connect(
                    self._database_url,
                    cursor_factory=psycopg2.extras.RealDictCursor,
                    timeout=timeout,
                )
            except psycopg2.Error as exc:
                logger.error("Failed to create new connection: %s", exc)
                raise

        return conn

    def put_connection(self, conn) -> None:
        """Return a connection to the pool."""
        self._pool.putconn(conn)

    @staticmethod
    def _is_healthy(conn) -> bool:
        """Check if a connection is still valid."""
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except (psycopg2.Error, Exception) as exc:
            logger.debug("Connection health check failed: %s", exc)
            return False

    def close(self) -> None:
        """Close all connections in the pool."""
        self._pool.closeall()
