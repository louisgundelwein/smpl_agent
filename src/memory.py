"""Semantic memory store with SQLite persistence and numpy vector search."""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

import numpy as np

from src.embeddings import EmbeddingClient


class MemoryStore:
    """Persistent semantic memory using SQLite + OpenAI embeddings.

    Stores text content with embedding vectors and optional tags.
    Supports hybrid search: cosine similarity + FTS5 keyword bonus.
    """

    def __init__(self, db_path: str, embedding_client: EmbeddingClient) -> None:
        self._embedding_client = embedding_client
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """Create tables and triggers if they don't exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                embedding BLOB NOT NULL,
                tags TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
            USING fts5(content, tags, content='memories', content_rowid='id');

            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories
            BEGIN
                INSERT INTO memories_fts(rowid, content, tags)
                VALUES (new.id, new.content, new.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories
            BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, tags)
                VALUES ('delete', old.id, old.content, old.tags);
            END;
        """)

    def add(self, content: str, tags: list[str] | None = None) -> int:
        """Store a memory with its embedding.

        Args:
            content: The text content to remember.
            tags: Optional list of tags for categorization.

        Returns:
            The ID of the stored memory.
        """
        vectors = self._embedding_client.embed([content])
        embedding_blob = np.array(vectors[0], dtype=np.float32).tobytes()
        tags_str = ",".join(tags) if tags else ""
        now = datetime.now(timezone.utc).isoformat()

        cursor = self._conn.execute(
            "INSERT INTO memories (content, embedding, tags, created_at) VALUES (?, ?, ?, ?)",
            (content, embedding_blob, tags_str, now),
        )
        self._conn.commit()
        return cursor.lastrowid

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Hybrid search: semantic similarity + FTS5 keyword matching.

        Args:
            query: Natural language search query.
            top_k: Maximum number of results to return.

        Returns:
            List of memory dicts sorted by relevance, each with keys:
            id, content, tags, created_at, score.
        """
        rows = self._conn.execute(
            "SELECT id, content, embedding, tags, created_at FROM memories"
        ).fetchall()

        if not rows:
            return []

        # Semantic scoring via numpy
        query_vector = np.array(
            self._embedding_client.embed([query])[0], dtype=np.float32
        )

        ids = []
        embeddings = []
        meta: dict[int, dict[str, Any]] = {}
        for row in rows:
            mem_id = row["id"]
            ids.append(mem_id)
            vec = np.frombuffer(row["embedding"], dtype=np.float32).copy()
            embeddings.append(vec)
            meta[mem_id] = {
                "id": mem_id,
                "content": row["content"],
                "tags": [t for t in row["tags"].split(",") if t],
                "created_at": row["created_at"],
            }

        embedding_matrix = np.stack(embeddings)

        # Cosine similarity
        norms = np.linalg.norm(embedding_matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        normalized = embedding_matrix / norms

        query_norm = np.linalg.norm(query_vector)
        if query_norm > 0:
            query_normalized = query_vector / query_norm
        else:
            query_normalized = query_vector

        semantic_scores = normalized @ query_normalized

        # FTS5 keyword scoring
        fts_ids: set[int] = set()
        try:
            fts_rows = self._conn.execute(
                "SELECT rowid FROM memories_fts WHERE memories_fts MATCH ?",
                (query,),
            ).fetchall()
            fts_ids = {row["rowid"] for row in fts_rows}
        except sqlite3.OperationalError:
            # FTS query syntax error (special characters). Semantic-only fallback.
            pass

        # Combine: semantic (0-1) + FTS bonus (0.1 if keyword match)
        FTS_BONUS = 0.1
        results = []
        for i, mem_id in enumerate(ids):
            score = float(semantic_scores[i])
            if mem_id in fts_ids:
                score += FTS_BONUS
            entry = meta[mem_id].copy()
            entry["score"] = round(score, 4)
            results.append(entry)

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def delete(self, memory_id: int) -> bool:
        """Delete a memory by ID.

        Returns:
            True if a memory was deleted, False if ID not found.
        """
        cursor = self._conn.execute(
            "DELETE FROM memories WHERE id = ?", (memory_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def count(self) -> int:
        """Return the total number of stored memories."""
        row = self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()
        return row[0]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
