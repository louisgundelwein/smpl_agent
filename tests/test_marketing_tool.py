"""Tests for MarketingTool."""

import json
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from src.marketing_store import MarketingStore
from src.tools.marketing import MarketingTool


@pytest.fixture
def mock_store():
    """Mock MarketingStore."""
    return MagicMock(spec=MarketingStore)


@pytest.fixture
def tool(mock_store):
    """MarketingTool with mocked store and no real browser/API calls."""
    return MarketingTool(
        store=mock_store,
        openai_api_key="test-key",
        openai_model="gpt-4o",
        openai_base_url=None,
        browser_timeout=60,
    )


class TestAccountActions:
    def test_add_account(self, tool, mock_store):
        mock_store.add_account.return_value = 1
        result = json.loads(tool.execute(
            action="add_account",
            name="reddit-main",
            platform="reddit",
            credentials={"username": "bot", "password": "pass"},
        ))
        assert result["added"] is True
        assert result["account_id"] == 1
        mock_store.add_account.assert_called_once()

    def test_add_account_missing_fields(self, tool):
        result = json.loads(tool.execute(action="add_account", name="x"))
        assert "error" in result

    def test_add_account_unsupported_platform(self, tool):
        result = json.loads(tool.execute(
            action="add_account",
            name="x",
            platform="tiktok",
            credentials={"username": "u"},
        ))
        assert "Unsupported platform" in result["error"]

    def test_list_accounts(self, tool, mock_store):
        mock_store.list_accounts.return_value = [
            {"id": 1, "name": "r1", "platform": "reddit"},
        ]
        result = json.loads(tool.execute(action="list_accounts"))
        assert result["count"] == 1

    def test_remove_account(self, tool, mock_store):
        mock_store.remove_account.return_value = True
        result = json.loads(tool.execute(action="remove_account", name="r1"))
        assert result["removed"] is True

    def test_remove_account_missing_name(self, tool):
        result = json.loads(tool.execute(action="remove_account"))
        assert "error" in result


class TestCreatePost:
    def test_create_post_success(self, tool, mock_store):
        mock_store.get_account.return_value = {
            "platform": "reddit",
            "credentials": {"username": "bot", "password": "pass"},
        }
        mock_store.create_post.return_value = 42

        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"url": "https://reddit.com/r/test/abc", "post_id": "abc"}'
            result = json.loads(tool.execute(
                action="create_post",
                account="reddit-main",
                content="Check out our app!",
                title="New App",
                subreddit="startups",
            ))

        assert result["posted"] is True
        assert result["post_id"] == 42
        mock_store.update_post_status.assert_called_once()

    def test_create_post_missing_fields(self, tool):
        result = json.loads(tool.execute(action="create_post"))
        assert "error" in result

    def test_create_post_account_not_found(self, tool, mock_store):
        mock_store.get_account.return_value = None
        result = json.loads(tool.execute(
            action="create_post", account="nope", content="hi",
        ))
        assert "not found" in result["error"]

    def test_create_post_browser_failure(self, tool, mock_store):
        mock_store.get_account.return_value = {
            "platform": "reddit",
            "credentials": {"username": "bot", "password": "pass"},
        }
        mock_store.create_post.return_value = 42

        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.side_effect = TimeoutError("Browser timed out")
            result = json.loads(tool.execute(
                action="create_post",
                account="reddit-main",
                content="test",
            ))

        assert result["posted"] is False
        assert "timed out" in result["error"]
        mock_store.update_post_status.assert_called_with(42, "failed", error="Browser timed out")

    def test_create_post_with_image(self, tool, mock_store):
        mock_store.get_account.return_value = {
            "platform": "twitter",
            "credentials": {"username": "bot", "password": "pass"},
        }
        mock_store.create_post.return_value = 10

        with patch.object(tool, "_generate_image", return_value="/tmp/img.png") as mock_img, \
             patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"url": "https://x.com/post/1"}'
            result = json.loads(tool.execute(
                action="create_post",
                account="twitter-bot",
                content="Look at this!",
                generate_image_prompt="a cool app screenshot",
            ))

        assert result["posted"] is True
        mock_img.assert_called_once_with("a cool app screenshot", "1024x1024")


class TestPostQueries:
    def test_list_posts(self, tool, mock_store):
        mock_store.list_posts.return_value = [{"id": 1}, {"id": 2}]
        result = json.loads(tool.execute(action="list_posts", platform="reddit"))
        assert result["count"] == 2

    def test_get_post(self, tool, mock_store):
        mock_store.get_post.return_value = {"id": 42, "content": "hello"}
        mock_store.get_metrics.return_value = [{"likes": 10}]
        result = json.loads(tool.execute(action="get_post", post_id=42))
        assert result["post"]["id"] == 42
        assert result["metrics"][0]["likes"] == 10

    def test_get_post_not_found(self, tool, mock_store):
        mock_store.get_post.return_value = None
        result = json.loads(tool.execute(action="get_post", post_id=999))
        assert "not found" in result["error"]

    def test_get_recent_content(self, tool, mock_store):
        mock_store.get_recent_content.return_value = ["post1", "post2"]
        result = json.loads(tool.execute(action="get_recent_content", platform="reddit"))
        assert result["count"] == 2


class TestMetrics:
    def test_fetch_metrics_success(self, tool, mock_store):
        mock_store.get_post.return_value = {
            "id": 42, "account_name": "r1", "platform": "reddit",
            "platform_post_id": "https://reddit.com/r/test/42",
        }
        mock_store.get_account.return_value = {
            "credentials": {"username": "u", "password": "p"},
        }
        mock_store.record_metrics.return_value = 7

        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = json.dumps({
                "likes": 15, "comments": 3, "shares": 0, "views": 0,
            })
            result = json.loads(tool.execute(action="fetch_metrics", post_id=42))

        assert result["fetched"] is True
        assert result["metric_id"] == 7

    def test_fetch_metrics_no_platform_id(self, tool, mock_store):
        mock_store.get_post.return_value = {
            "id": 42, "platform_post_id": None,
        }
        result = json.loads(tool.execute(action="fetch_metrics", post_id=42))
        assert "not yet posted" in result["error"]

    def test_get_performance(self, tool, mock_store):
        mock_store.get_performance_summary.return_value = {
            "total_posts": 5, "total_likes": 50, "days": 7,
        }
        result = json.loads(tool.execute(
            action="get_performance", platform="reddit", days=7,
        ))
        assert result["performance"]["total_posts"] == 5


class TestComments:
    def test_get_comments(self, tool, mock_store):
        mock_store.get_post.return_value = {
            "id": 42, "account_name": "r1", "platform": "reddit",
            "platform_post_id": "https://reddit.com/42",
        }
        mock_store.get_account.return_value = {
            "credentials": {"username": "u", "password": "p"},
        }

        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = json.dumps({
                "comments": [{"id": "c1", "author": "user1", "text": "great!"}],
            })
            result = json.loads(tool.execute(action="get_comments", post_id=42))

        assert len(result["comments"]) == 1

    def test_reply_comment(self, tool, mock_store):
        mock_store.get_post.return_value = {
            "id": 42, "account_name": "r1", "platform": "reddit",
            "platform_post_id": "https://reddit.com/42",
        }
        mock_store.get_account.return_value = {
            "credentials": {"username": "u", "password": "p"},
        }

        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = json.dumps({"replied": True, "comment_id": "c1"})
            result = json.loads(tool.execute(
                action="reply_comment",
                post_id=42,
                comment_id="c1",
                body="Thanks!",
            ))

        assert result["replied"] is True

    def test_reply_comment_missing_fields(self, tool):
        result = json.loads(tool.execute(action="reply_comment", post_id=42))
        assert "error" in result


class TestDeletePost:
    def test_delete_posted_post(self, tool, mock_store):
        mock_store.get_post.return_value = {
            "id": 42, "account_name": "r1", "platform": "reddit",
            "platform_post_id": "https://reddit.com/42",
        }
        mock_store.get_account.return_value = {
            "credentials": {"username": "u", "password": "p"},
        }

        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"deleted": true}'
            result = json.loads(tool.execute(action="delete_post", post_id=42))

        assert result["deleted"] is True
        mock_store.update_post_status.assert_called_with(42, "deleted")

    def test_delete_draft_post(self, tool, mock_store):
        mock_store.get_post.return_value = {
            "id": 42, "account_name": "r1", "platform": "reddit",
            "platform_post_id": None,
        }
        result = json.loads(tool.execute(action="delete_post", post_id=42))
        assert result["deleted"] is True


class TestGenerateImage:
    def test_generate_image_action(self, tool):
        with patch.object(tool, "_generate_image", return_value="/tmp/img.png"):
            result = json.loads(tool.execute(
                action="generate_image", prompt="a sunset",
            ))
        assert result["generated"] is True
        assert result["path"] == "/tmp/img.png"

    def test_generate_image_missing_prompt(self, tool):
        result = json.loads(tool.execute(action="generate_image"))
        assert "error" in result

    def test_generate_image_failure(self, tool):
        with patch.object(tool, "_generate_image", side_effect=Exception("API error")):
            result = json.loads(tool.execute(
                action="generate_image", prompt="a sunset",
            ))
        assert "Image generation failed" in result["error"]


class TestUnknownAction:
    def test_unknown_action(self, tool):
        result = json.loads(tool.execute(action="foobar"))
        assert "Unknown action" in result["error"]
