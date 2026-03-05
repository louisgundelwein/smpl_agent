"""Semantic memory store with Postgres/pgvector persistence."""

import json
from typing import Any

from src.db import Database
from src.embeddings import EmbeddingClient


class MemoryStore:
    """Persistent semantic memory using Postgres + pgvector.

    Stores text content with embedding vectors and optional metadata.
    Supports hybrid search: pgvector cosine similarity + tsvector keyword bonus.
    """

    def __init__(self, db: Database, embedding_client: EmbeddingClient, dimensions: int = 1536) -> None:
        self._embedding_client = embedding_client
        self._db = db
        self._dimensions = dimensions
        self._init_schema()

    def _init_schema(self) -> None:
        """Create tables and indexes if they don't exist."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS memories (
                        id SERIAL PRIMARY KEY,
                        content TEXT NOT NULL,
                        embedding vector({self._dimensions}) NOT NULL,
                        metadata JSONB DEFAULT '{{}}',
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS memories_embedding_hnsw_idx
                        ON memories USING hnsw (embedding vector_cosine_ops)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS memories_content_fts_idx
                        ON memories USING gin (to_tsvector('english', content))
                """)
            conn.commit()
        finally:
            self._db.put_connection(conn)

    def add(self, content: str, tags: list[str] | None = None) -> int:
        """Store a memory with its embedding.

        Args:
            content: The text content to remember.
            tags: Optional list of tags for categorization (stored in metadata).

        Returns:
            The ID of the stored memory.
        """
        vectors = self._embedding_client.embed([content])
        embedding_str = json.dumps(vectors[0])
        metadata = json.dumps({"tags": tags or []})

        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO memories (content, embedding, metadata) VALUES (%s, %s::vector, %s::jsonb) RETURNING id",
                    (content, embedding_str, metadata),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"]
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.put_connection(conn)

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Hybrid search: pgvector cosine similarity + tsvector keyword matching.

        Args:
            query: Natural language search query.
            top_k: Maximum number of results to return.

        Returns:
            List of memory dicts sorted by relevance, each with keys:
            id, content, tags, created_at, score.
        """
        query_vector = self._embedding_client.embed([query])[0]
        query_embedding_str = json.dumps(query_vector)

        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT * FROM (
                           SELECT id, content, metadata, created_at,
                                  1 - (embedding <=> %s::vector) AS semantic_score,
                                  CASE WHEN to_tsvector('english', content) @@ plainto_tsquery('english', %s)
                                       THEN 0.1 ELSE 0.0 END AS fts_bonus
                           FROM memories
                       ) sub
                       ORDER BY semantic_score + fts_bonus DESC
                       LIMIT %s""",
                    (query_embedding_str, query, top_k),
                )
                rows = cur.fetchall()
            return [
                {
                    "id": row["id"],
                    "content": row["content"],
                    "tags": (row["metadata"] or {}).get("tags", []),
                    "created_at": str(row["created_at"]),
                    "score": round(float(row["semantic_score"]) + float(row["fts_bonus"]), 4),
                }
                for row in rows
            ]
        finally:
            self._db.put_connection(conn)

    def delete(self, memory_id: int) -> bool:
        """Delete a memory by ID.

        Returns:
            True if a memory was deleted, False if ID not found.
        """
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM memories WHERE id = %s", (memory_id,)
                )
                deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        finally:
            self._db.put_connection(conn)

    def count(self) -> int:
        """Return the total number of stored memories."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM memories")
                row = cur.fetchone()
            return row["cnt"]
        finally:
            self._db.put_connection(conn)

    def find_duplicate_groups(
        self, threshold: float = 0.90
    ) -> list[list[dict[str, Any]]]:
        """Find groups of near-duplicate memories via pgvector cosine similarity.

        Uses a self-join on the memories table to find all pairs with
        similarity above the threshold, then groups them using union-find.

        Args:
            threshold: Minimum cosine similarity to consider a duplicate (0-1).

        Returns:
            List of groups, where each group is a list of memory dicts
            (id, content, tags, created_at). Only groups with 2+ members.
        """
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT m1.id AS id1, m2.id AS id2
                       FROM memories m1
                       JOIN memories m2 ON m1.id < m2.id
                       WHERE 1 - (m1.embedding <=> m2.embedding) > %s""",
                    (threshold,),
                )
                pairs = cur.fetchall()

            if not pairs:
                return []

            # Union-find to group connected IDs.
            parent: dict[int, int] = {}

            def find(x: int) -> int:
                while parent.get(x, x) != x:
                    parent[x] = parent.get(parent[x], parent[x])
                    x = parent[x]
                return x

            def union(a: int, b: int) -> None:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[ra] = rb

            for pair in pairs:
                union(pair["id1"], pair["id2"])

            # Collect groups.
            groups_map: dict[int, list[int]] = {}
            all_ids = set()
            for pair in pairs:
                all_ids.add(pair["id1"])
                all_ids.add(pair["id2"])
            for mid in all_ids:
                root = find(mid)
                groups_map.setdefault(root, []).append(mid)

            # Deduplicate IDs within each group.
            groups_map = {
                root: sorted(set(ids)) for root, ids in groups_map.items()
            }

            # Fetch full memory data for each group.
            result: list[list[dict[str, Any]]] = []
            with conn.cursor() as cur:
                for ids in groups_map.values():
                    if len(ids) < 2:
                        continue
                    cur.execute(
                        "SELECT id, content, metadata, created_at FROM memories WHERE id = ANY(%s) ORDER BY id",
                        (ids,),
                    )
                    rows = cur.fetchall()
                    group = [
                        {
                            "id": row["id"],
                            "content": row["content"],
                            "tags": (row["metadata"] or {}).get("tags", []),
                            "created_at": str(row["created_at"]),
                        }
                        for row in rows
                    ]
                    if len(group) >= 2:
                        result.append(group)
            return result
        finally:
            self._db.put_connection(conn)

    def close(self) -> None:
        """No-op — connection pool is managed by Database."""
