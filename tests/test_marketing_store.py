"""Tests for MarketingStore."""

import json
from unittest.mock import MagicMock

import pytest

from src.marketing_store import MarketingStore


@pytest.fixture
def mock_db():
    """Mock Database with cursor context manager."""
    db = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    db.get_connection.return_value = conn
    db._mock_conn = conn
    db._mock_cursor = cursor
    return db


@pytest.fixture
def store(mock_db):
    """MarketingStore backed by mock DB."""
    return MarketingStore(mock_db)


class TestInitSchema:
    def test_creates_tables_on_init(self, mock_db, store):
        """Schema init runs CREATE TABLE statements."""
        calls = mock_db._mock_cursor.execute.call_args_list
        sql_stmts = [c[0][0] for c in calls]
        assert any("marketing_accounts" in s for s in sql_stmts)
        assert any("marketing_posts" in s for s in sql_stmts)
        assert any("marketing_metrics" in s for s in sql_stmts)
        mock_db._mock_conn.commit.assert_called()


class TestAccounts:
    def test_add_account(self, store, mock_db):
        mock_db._mock_cursor.fetchone.return_value = {"id": 1}
        result = store.add_account(
            name="reddit-main",
            platform="reddit",
            credentials={"username": "bot", "password": "pass"},
        )
        assert result == 1
        mock_db._mock_cursor.execute.assert_called()
        args = mock_db._mock_cursor.execute.call_args[0]
        assert "INSERT INTO marketing_accounts" in args[0]
        assert args[1][0] == "reddit-main"
        assert args[1][1] == "reddit"

    def test_list_accounts(self, store, mock_db):
        mock_db._mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "reddit-main", "platform": "reddit",
             "config": {}, "added_at": "2024-01-01"},
        ]
        result = store.list_accounts()
        assert len(result) == 1
        assert result[0]["name"] == "reddit-main"

    def test_get_account(self, store, mock_db):
        mock_db._mock_cursor.fetchone.return_value = {
            "id": 1, "name": "reddit-main", "platform": "reddit",
            "credentials": {"username": "bot"}, "config": {},
            "added_at": "2024-01-01",
        }
        result = store.get_account("reddit-main")
        assert result["name"] == "reddit-main"
        assert result["credentials"]["username"] == "bot"

    def test_get_account_not_found(self, store, mock_db):
        mock_db._mock_cursor.fetchone.return_value = None
        result = store.get_account("nonexistent")
        assert result is None

    def test_remove_account(self, store, mock_db):
        mock_db._mock_cursor.rowcount = 1
        assert store.remove_account("reddit-main") is True

    def test_remove_account_not_found(self, store, mock_db):
        mock_db._mock_cursor.rowcount = 0
        assert store.remove_account("nonexistent") is False


class TestPosts:
    def test_create_post(self, store, mock_db):
        mock_db._mock_cursor.fetchone.return_value = {"id": 42}
        result = store.create_post(
            account_name="reddit-main",
            platform="reddit",
            content="Check out our app!",
            title="New App Launch",
            subreddit="startups",
            campaign="launch-2024",
        )
        assert result == 42
        args = mock_db._mock_cursor.execute.call_args[0]
        assert "INSERT INTO marketing_posts" in args[0]

    def test_update_post_status_posted(self, store, mock_db):
        mock_db._mock_cursor.rowcount = 1
        result = store.update_post_status(
            post_id=42, status="posted",
            platform_post_id="https://reddit.com/r/test/123",
        )
        assert result is True

    def test_update_post_status_failed(self, store, mock_db):
        mock_db._mock_cursor.rowcount = 1
        result = store.update_post_status(
            post_id=42, status="failed", error="Browser timeout",
        )
        assert result is True

    def test_get_post(self, store, mock_db):
        mock_db._mock_cursor.fetchone.return_value = {
            "id": 42, "account_name": "reddit-main", "platform": "reddit",
            "content": "Hello", "status": "posted",
        }
        result = store.get_post(42)
        assert result["id"] == 42
        assert result["status"] == "posted"

    def test_list_posts_no_filters(self, store, mock_db):
        mock_db._mock_cursor.fetchall.return_value = [
            {"id": 1, "content": "post1"},
            {"id": 2, "content": "post2"},
        ]
        result = store.list_posts()
        assert len(result) == 2

    def test_list_posts_with_filters(self, store, mock_db):
        mock_db._mock_cursor.fetchall.return_value = []
        store.list_posts(
            account_name="reddit-main",
            platform="reddit",
            campaign="launch",
            status="posted",
            limit=5,
        )
        args = mock_db._mock_cursor.execute.call_args[0]
        assert "account_name = %s" in args[0]
        assert "platform = %s" in args[0]
        assert "campaign = %s" in args[0]
        assert "status = %s" in args[0]
        assert args[1] == ["reddit-main", "reddit", "launch", "posted", 5]

    def test_get_recent_content(self, store, mock_db):
        mock_db._mock_cursor.fetchall.return_value = [
            {"content": "post A"},
            {"content": "post B"},
        ]
        result = store.get_recent_content(platform="reddit", limit=10)
        assert result == ["post A", "post B"]


class TestMetrics:
    def test_record_metrics(self, store, mock_db):
        mock_db._mock_cursor.fetchone.return_value = {"id": 7}
        result = store.record_metrics(
            post_id=42, likes=10, comments=3, shares=1, views=500,
            extra={"upvote_ratio": 0.95},
        )
        assert result == 7
        args = mock_db._mock_cursor.execute.call_args[0]
        assert "INSERT INTO marketing_metrics" in args[0]

    def test_get_metrics(self, store, mock_db):
        mock_db._mock_cursor.fetchall.return_value = [
            {"id": 1, "post_id": 42, "likes": 5, "fetched_at": "t1"},
            {"id": 2, "post_id": 42, "likes": 10, "fetched_at": "t2"},
        ]
        result = store.get_metrics(42)
        assert len(result) == 2
        assert result[1]["likes"] == 10

    def test_get_performance_summary(self, store, mock_db):
        mock_db._mock_cursor.fetchone.return_value = {
            "total_posts": 10,
            "total_likes": 100,
            "total_comments": 30,
            "total_shares": 5,
            "total_views": 5000,
        }
        result = store.get_performance_summary(platform="reddit", days=7)
        assert result["total_posts"] == 10
        assert result["avg_likes"] == 10.0
        assert result["days"] == 7

    def test_get_performance_summary_no_posts(self, store, mock_db):
        mock_db._mock_cursor.fetchone.return_value = {
            "total_posts": 0,
            "total_likes": 0,
            "total_comments": 0,
            "total_shares": 0,
            "total_views": 0,
        }
        result = store.get_performance_summary()
        assert result["total_posts"] == 0
        assert "avg_likes" not in result
