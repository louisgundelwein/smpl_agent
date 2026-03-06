"""Marketing account, post, and metrics registry with Postgres persistence."""

import json
from datetime import datetime, timezone
from typing import Any

from src.db import Database


class MarketingStore:
    """Persistent marketing data store using Postgres.

    Manages platform accounts (credentials), posts (drafts/published),
    and engagement metrics (time-series snapshots).
    """

    def __init__(self, db: Database) -> None:
        self._db = db
        self._init_schema()

    def _init_schema(self) -> None:
        """Create marketing tables if they don't exist."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS marketing_accounts (
                        id          SERIAL PRIMARY KEY,
                        name        TEXT NOT NULL UNIQUE,
                        platform    TEXT NOT NULL,
                        credentials JSONB NOT NULL DEFAULT '{}',
                        config      JSONB NOT NULL DEFAULT '{}',
                        added_at    TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS marketing_posts (
                        id               SERIAL PRIMARY KEY,
                        account_name     TEXT NOT NULL,
                        platform         TEXT NOT NULL,
                        campaign         TEXT,
                        title            TEXT,
                        content          TEXT NOT NULL,
                        url              TEXT,
                        image_path       TEXT,
                        platform_post_id TEXT,
                        subreddit        TEXT,
                        status           TEXT NOT NULL DEFAULT 'draft',
                        error_message    TEXT,
                        posted_at        TIMESTAMPTZ,
                        created_at       TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS marketing_posts_account_idx
                        ON marketing_posts(account_name)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS marketing_posts_platform_idx
                        ON marketing_posts(platform)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS marketing_posts_campaign_idx
                        ON marketing_posts(campaign)
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS marketing_metrics (
                        id          SERIAL PRIMARY KEY,
                        post_id     INTEGER NOT NULL REFERENCES marketing_posts(id) ON DELETE CASCADE,
                        likes       INTEGER DEFAULT 0,
                        comments    INTEGER DEFAULT 0,
                        shares      INTEGER DEFAULT 0,
                        views       INTEGER DEFAULT 0,
                        extra       JSONB DEFAULT '{}',
                        fetched_at  TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS marketing_metrics_post_idx
                        ON marketing_metrics(post_id)
                """)
            conn.commit()
        finally:
            self._db.put_connection(conn)

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    def add_account(
        self,
        name: str,
        platform: str,
        credentials: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> int:
        """Register a new platform account.

        Args:
            name: Unique short name (e.g. "reddit-main").
            platform: Platform identifier (reddit/twitter/linkedin/instagram).
            credentials: Login details (username, password, etc.).
            config: Optional platform-specific config (default subreddits, hashtags).

        Returns:
            The ID of the stored account.
        """
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO marketing_accounts
                       (name, platform, credentials, config)
                       VALUES (%s, %s, %s, %s) RETURNING id""",
                    (name, platform,
                     json.dumps(credentials),
                     json.dumps(config or {})),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"]
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.put_connection(conn)

    def list_accounts(self) -> list[dict[str, Any]]:
        """Return all registered accounts (credentials redacted)."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, platform, config, added_at "
                    "FROM marketing_accounts ORDER BY name"
                )
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._db.put_connection(conn)

    def get_account(self, name: str) -> dict[str, Any] | None:
        """Get an account by name (includes credentials for auth)."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, platform, credentials, config, added_at "
                    "FROM marketing_accounts WHERE name = %s",
                    (name,),
                )
                row = cur.fetchone()
            return dict(row) if row else None
        finally:
            self._db.put_connection(conn)

    def remove_account(self, name: str) -> bool:
        """Remove an account by name. Returns True if removed."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM marketing_accounts WHERE name = %s", (name,),
                )
                removed = cur.rowcount > 0
            conn.commit()
            return removed
        finally:
            self._db.put_connection(conn)

    # ------------------------------------------------------------------
    # Posts
    # ------------------------------------------------------------------

    def create_post(
        self,
        account_name: str,
        platform: str,
        content: str,
        title: str | None = None,
        url: str | None = None,
        image_path: str | None = None,
        subreddit: str | None = None,
        campaign: str | None = None,
    ) -> int:
        """Create a new post record (status='draft').

        Returns:
            The post ID.
        """
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO marketing_posts
                       (account_name, platform, content, title, url,
                        image_path, subreddit, campaign, status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'draft')
                       RETURNING id""",
                    (account_name, platform, content, title, url,
                     image_path, subreddit, campaign),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"]
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.put_connection(conn)

    def update_post_status(
        self,
        post_id: int,
        status: str,
        platform_post_id: str | None = None,
        error: str | None = None,
    ) -> bool:
        """Update a post's status.

        Args:
            post_id: The post to update.
            status: New status (draft/posted/failed/deleted).
            platform_post_id: Platform-assigned ID/URL (on success).
            error: Error message (on failure).

        Returns:
            True if the post was found and updated.
        """
        now = datetime.now(timezone.utc).isoformat()
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE marketing_posts
                       SET status = %s,
                           platform_post_id = COALESCE(%s, platform_post_id),
                           error_message = %s,
                           posted_at = CASE WHEN %s = 'posted' THEN %s ELSE posted_at END
                       WHERE id = %s""",
                    (status, platform_post_id, error, status, now, post_id),
                )
                updated = cur.rowcount > 0
            conn.commit()
            return updated
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.put_connection(conn)

    def get_post(self, post_id: int) -> dict[str, Any] | None:
        """Get a single post by ID."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM marketing_posts WHERE id = %s",
                    (post_id,),
                )
                row = cur.fetchone()
            return dict(row) if row else None
        finally:
            self._db.put_connection(conn)

    def list_posts(
        self,
        account_name: str | None = None,
        platform: str | None = None,
        campaign: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List posts with optional filters."""
        conditions: list[str] = []
        params: list[Any] = []

        if account_name:
            conditions.append("account_name = %s")
            params.append(account_name)
        if platform:
            conditions.append("platform = %s")
            params.append(platform)
        if campaign:
            conditions.append("campaign = %s")
            params.append(campaign)
        if status:
            conditions.append("status = %s")
            params.append(status)

        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(limit)

        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM marketing_posts{where} "
                    f"ORDER BY created_at DESC LIMIT %s",
                    params,
                )
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._db.put_connection(conn)

    def get_recent_content(
        self,
        platform: str | None = None,
        limit: int = 50,
    ) -> list[str]:
        """Return recent post content strings for anti-repetition."""
        params: list[Any] = []
        where = ""
        if platform:
            where = " WHERE platform = %s"
            params.append(platform)
        params.append(limit)

        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT content FROM marketing_posts{where} "
                    f"ORDER BY created_at DESC LIMIT %s",
                    params,
                )
                rows = cur.fetchall()
            return [row["content"] for row in rows]
        finally:
            self._db.put_connection(conn)

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def record_metrics(
        self,
        post_id: int,
        likes: int = 0,
        comments: int = 0,
        shares: int = 0,
        views: int = 0,
        extra: dict[str, Any] | None = None,
    ) -> int:
        """Record an engagement snapshot for a post.

        Returns:
            The metric record ID.
        """
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO marketing_metrics
                       (post_id, likes, comments, shares, views, extra)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                    (post_id, likes, comments, shares, views,
                     json.dumps(extra or {})),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"]
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.put_connection(conn)

    def get_metrics(self, post_id: int) -> list[dict[str, Any]]:
        """Get all metric snapshots for a post, ordered by time."""
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM marketing_metrics WHERE post_id = %s "
                    "ORDER BY fetched_at",
                    (post_id,),
                )
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._db.put_connection(conn)

    def get_performance_summary(
        self,
        account_name: str | None = None,
        platform: str | None = None,
        campaign: str | None = None,
        days: int = 30,
    ) -> dict[str, Any]:
        """Aggregate performance report over a time window.

        Returns totals and averages for likes, comments, shares, views
        across matching posts.
        """
        conditions = ["p.status = 'posted'"]
        params: list[Any] = []

        conditions.append("p.posted_at >= NOW() - INTERVAL '%s days'")
        params.append(days)

        if account_name:
            conditions.append("p.account_name = %s")
            params.append(account_name)
        if platform:
            conditions.append("p.platform = %s")
            params.append(platform)
        if campaign:
            conditions.append("p.campaign = %s")
            params.append(campaign)

        where = " WHERE " + " AND ".join(conditions)

        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                # Get latest metrics per post (most recent snapshot only)
                cur.execute(
                    f"""SELECT
                            COUNT(DISTINCT p.id) AS total_posts,
                            COALESCE(SUM(m.likes), 0) AS total_likes,
                            COALESCE(SUM(m.comments), 0) AS total_comments,
                            COALESCE(SUM(m.shares), 0) AS total_shares,
                            COALESCE(SUM(m.views), 0) AS total_views
                        FROM marketing_posts p
                        LEFT JOIN LATERAL (
                            SELECT likes, comments, shares, views
                            FROM marketing_metrics
                            WHERE post_id = p.id
                            ORDER BY fetched_at DESC
                            LIMIT 1
                        ) m ON true
                        {where}""",
                    params,
                )
                row = cur.fetchone()
            result = dict(row) if row else {}
            total_posts = result.get("total_posts", 0)
            if total_posts > 0:
                result["avg_likes"] = round(result["total_likes"] / total_posts, 1)
                result["avg_comments"] = round(result["total_comments"] / total_posts, 1)
                result["avg_shares"] = round(result["total_shares"] / total_posts, 1)
                result["avg_views"] = round(result["total_views"] / total_posts, 1)
            result["days"] = days
            return result
        finally:
            self._db.put_connection(conn)

    # ------------------------------------------------------------------
    # Drafts
    # ------------------------------------------------------------------

    def _init_drafts_schema(self) -> None:
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS post_drafts (
                        id          SERIAL PRIMARY KEY,
                        account_id  INTEGER REFERENCES marketing_accounts(id) ON DELETE CASCADE,
                        post_type   TEXT NOT NULL DEFAULT 'text',
                        title       TEXT,
                        content     TEXT NOT NULL,
                        metadata    JSONB DEFAULT '{}',
                        created_at  TIMESTAMPTZ DEFAULT NOW(),
                        updated_at  TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS linkedin_profile_metrics (
                        id               SERIAL PRIMARY KEY,
                        account_id       INTEGER REFERENCES marketing_accounts(id) ON DELETE CASCADE,
                        profile_views    INTEGER,
                        ssi_score        INTEGER,
                        follower_count   INTEGER,
                        connection_count INTEGER,
                        recorded_at      TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
            conn.commit()
        finally:
            self._db.put_connection(conn)

    def create_draft(
        self,
        account_id: int,
        content: str,
        post_type: str = "text",
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO post_drafts
                       (account_id, post_type, title, content, metadata)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                    (account_id, post_type, title, content,
                     json.dumps(metadata or {})),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"]
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.put_connection(conn)

    def list_drafts(self, account_id: int | None = None) -> list[dict[str, Any]]:
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                if account_id:
                    cur.execute(
                        "SELECT * FROM post_drafts WHERE account_id = %s "
                        "ORDER BY updated_at DESC",
                        (account_id,),
                    )
                else:
                    cur.execute("SELECT * FROM post_drafts ORDER BY updated_at DESC")
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._db.put_connection(conn)

    def get_draft(self, draft_id: int) -> dict[str, Any] | None:
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM post_drafts WHERE id = %s", (draft_id,))
                row = cur.fetchone()
            return dict(row) if row else None
        finally:
            self._db.put_connection(conn)

    def update_draft(
        self,
        draft_id: int,
        content: str | None = None,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        sets = ["updated_at = NOW()"]
        params: list[Any] = []
        if content is not None:
            sets.append("content = %s")
            params.append(content)
        if title is not None:
            sets.append("title = %s")
            params.append(title)
        if metadata is not None:
            sets.append("metadata = %s")
            params.append(json.dumps(metadata))
        params.append(draft_id)

        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE post_drafts SET {', '.join(sets)} WHERE id = %s",
                    params,
                )
                updated = cur.rowcount > 0
            conn.commit()
            return updated
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.put_connection(conn)

    def delete_draft(self, draft_id: int) -> bool:
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM post_drafts WHERE id = %s", (draft_id,))
                deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        finally:
            self._db.put_connection(conn)

    # ------------------------------------------------------------------
    # LinkedIn Profile Metrics
    # ------------------------------------------------------------------

    def record_profile_metrics(
        self,
        account_id: int,
        profile_views: int | None = None,
        ssi_score: int | None = None,
        follower_count: int | None = None,
        connection_count: int | None = None,
    ) -> int:
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO linkedin_profile_metrics
                       (account_id, profile_views, ssi_score, follower_count, connection_count)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                    (account_id, profile_views, ssi_score, follower_count, connection_count),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"]
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.put_connection(conn)

    def get_profile_metrics_history(
        self,
        account_id: int,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM linkedin_profile_metrics "
                    "WHERE account_id = %s AND recorded_at >= NOW() - INTERVAL '%s days' "
                    "ORDER BY recorded_at",
                    (account_id, days),
                )
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._db.put_connection(conn)

    # ------------------------------------------------------------------
    # Reddit Profile Metrics
    # ------------------------------------------------------------------

    def record_reddit_profile_metrics(
        self,
        account_id: int,
        post_karma: int | None = None,
        comment_karma: int | None = None,
        total_karma: int | None = None,
        account_age_days: int | None = None,
    ) -> int:
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO reddit_profile_metrics
                       (account_id, post_karma, comment_karma, total_karma, account_age_days)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                    (account_id, post_karma, comment_karma, total_karma, account_age_days),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"]
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.put_connection(conn)

    def get_reddit_profile_metrics_history(
        self,
        account_id: int,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM reddit_profile_metrics "
                    "WHERE account_id = %s AND recorded_at >= NOW() - INTERVAL '%s days' "
                    "ORDER BY recorded_at",
                    (account_id, days),
                )
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._db.put_connection(conn)

    # ------------------------------------------------------------------
    # Instagram Profile Metrics
    # ------------------------------------------------------------------

    def record_instagram_profile_metrics(
        self,
        account_id: int,
        followers: int | None = None,
        following: int | None = None,
        posts_count: int | None = None,
        engagement_rate: float | None = None,
    ) -> int:
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO instagram_profile_metrics
                       (account_id, followers, following, posts_count, engagement_rate)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                    (account_id, followers, following, posts_count, engagement_rate),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"]
        except Exception:
            conn.rollback()
            raise
        finally:
            self._db.put_connection(conn)

    def get_instagram_profile_metrics_history(
        self,
        account_id: int,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        conn = self._db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM instagram_profile_metrics "
                    "WHERE account_id = %s AND recorded_at >= NOW() - INTERVAL '%s days' "
                    "ORDER BY recorded_at",
                    (account_id, days),
                )
                rows = cur.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._db.put_connection(conn)

    def close(self) -> None:
        """No-op — connection pool is managed by Database."""
