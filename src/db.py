"""Postgres connection pool via psycopg2."""

import psycopg2
import psycopg2.extras
import psycopg2.pool


class Database:
    """Thread-safe Postgres connection pool.

    Each store retrieves a connection via get_connection() and returns it
    via put_connection() when done. Connections use RealDictCursor by default.
    """

    def __init__(self, database_url: str, minconn: int = 1, maxconn: int = 10) -> None:
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn,
            maxconn,
            database_url,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )

    def get_connection(self):
        """Get a connection from the pool."""
        return self._pool.getconn()

    def put_connection(self, conn) -> None:
        """Return a connection to the pool."""
        self._pool.putconn(conn)

    def close(self) -> None:
        """Close all connections in the pool."""
        self._pool.closeall()
