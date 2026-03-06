"""Tests for RedditTool."""

import json
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from src.email_store import EmailAccountStore
from src.marketing.reddit import RedditAdapter
from src.marketing.platform_knowledge import PlatformKnowledge
from src.marketing_store import MarketingStore
from src.tools.reddit import RedditTool


@pytest.fixture
def mock_store():
    return MagicMock(spec=MarketingStore)


@pytest.fixture
def mock_email_store():
    return MagicMock(spec=EmailAccountStore)


@pytest.fixture
def mock_knowledge():
    k = MagicMock(spec=PlatformKnowledge)
    k.enhance_task.side_effect = lambda platform, task, context_keys=None: task
    k.get_guide.return_value = ""
    k.get_learnings.return_value = {}
    return k


@pytest.fixture
def mock_adapter(mock_knowledge):
    return RedditAdapter(knowledge=None)


@pytest.fixture
def tool(mock_store, mock_knowledge, mock_adapter, mock_email_store, tmp_path):
    return RedditTool(
        store=mock_store,
        knowledge=mock_knowledge,
        adapter=mock_adapter,
        openai_api_key="test-key",
        openai_model="gpt-4o",
        openai_base_url=None,
        timeout=60,
        action_delay=0,
        browser_profiles_dir=str(tmp_path / "profiles"),
        email_store=mock_email_store,
    )


@pytest.fixture
def tool_no_email(mock_store, mock_knowledge, mock_adapter, tmp_path):
    return RedditTool(
        store=mock_store,
        knowledge=mock_knowledge,
        adapter=mock_adapter,
        openai_api_key="test-key",
        openai_model="gpt-4o",
        openai_base_url=None,
        timeout=60,
        action_delay=0,
        browser_profiles_dir=str(tmp_path / "profiles"),
        email_store=None,
    )


@pytest.fixture
def reddit_account():
    return {
        "id": 1,
        "name": "rd-main",
        "platform": "reddit",
        "credentials": {"username": "testuser", "password": "pass123"},
        "config": {},
    }


class TestDispatch:
    def test_unknown_action(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(action="foobar", account="rd-main"))
        assert "Unknown action" in result["error"]

    def test_missing_account(self, tool, mock_store):
        mock_store.get_account.return_value = None
        result = json.loads(tool.execute(action="browse_feed", account="nope"))
        assert "not found" in result["error"]

    def test_wrong_platform(self, tool, mock_store):
        mock_store.get_account.return_value = {
            "id": 1, "name": "li-main", "platform": "linkedin",
            "credentials": {}, "config": {},
        }
        result = json.loads(tool.execute(action="browse_feed", account="li-main"))
        assert "not a Reddit account" in result["error"]


class TestFeedActions:
    def test_browse_feed(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"posts": [{"title": "Hello"}]}'
            result = json.loads(tool.execute(
                action="browse_feed", account="rd-main", query="python",
            ))
        assert "posts" in result

    def test_browse_subreddit(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"subreddit": "python", "posts": [{"title": "Hello"}]}'
            result = json.loads(tool.execute(
                action="browse_subreddit", account="rd-main",
                subreddit="python", sort="new",
            ))
        assert "posts" in result

    def test_browse_subreddit_missing(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(action="browse_subreddit", account="rd-main"))
        assert "error" in result

    def test_search_posts(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"posts": [{"title": "Found it"}]}'
            result = json.loads(tool.execute(
                action="search_posts", account="rd-main", query="AI tools",
            ))
        assert "posts" in result

    def test_search_posts_missing_query(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(action="search_posts", account="rd-main"))
        assert "error" in result


class TestInteractionActions:
    def test_upvote(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"voted": true, "direction": "up"}'
            result = json.loads(tool.execute(
                action="upvote", account="rd-main",
                post_url="https://reddit.com/r/test/comments/abc/post",
            ))
        assert result["voted"] is True

    def test_upvote_missing_url(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(action="upvote", account="rd-main"))
        assert "error" in result

    def test_downvote(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"voted": true, "direction": "down"}'
            result = json.loads(tool.execute(
                action="downvote", account="rd-main",
                post_url="https://reddit.com/r/test/comments/abc/post",
            ))
        assert result["voted"] is True

    def test_comment(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"commented": true}'
            result = json.loads(tool.execute(
                action="comment", account="rd-main",
                post_url="https://reddit.com/r/test/comments/abc/post",
                content="Great post!",
            ))
        assert result["commented"] is True

    def test_comment_missing_fields(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(
            action="comment", account="rd-main",
        ))
        assert "error" in result

    def test_reply_to_comment(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"replied": true}'
            result = json.loads(tool.execute(
                action="reply_to_comment", account="rd-main",
                post_url="https://reddit.com/r/test/comments/abc/post",
                comment_id="xyz123", content="Thanks!",
            ))
        assert result["replied"] is True

    def test_reply_to_comment_missing_fields(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(
            action="reply_to_comment", account="rd-main",
            post_url="https://reddit.com/r/test/comments/abc/post",
        ))
        assert "error" in result


class TestContentActions:
    def test_create_text_post(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"url": "https://reddit.com/r/test/comments/new"}'
            result = json.loads(tool.execute(
                action="create_post", account="rd-main",
                subreddit="python", content="Hello Reddit!",
                title="My First Post",
            ))
        assert "url" in result

    def test_create_post_missing_subreddit(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(
            action="create_post", account="rd-main", content="Hello",
        ))
        assert "subreddit is required" in result["error"]

    def test_create_post_missing_content(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(
            action="create_post", account="rd-main", subreddit="test",
        ))
        assert "error" in result

    def test_create_link_post(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"url": "https://reddit.com/r/test/comments/link"}'
            result = json.loads(tool.execute(
                action="create_post", account="rd-main",
                subreddit="python", post_type="link",
                title="Cool site", url="https://example.com",
            ))
        assert "url" in result

    def test_create_link_post_missing_url(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(
            action="create_post", account="rd-main",
            subreddit="python", post_type="link",
        ))
        assert "url is required" in result["error"]

    def test_create_image_post(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"url": "https://reddit.com/r/test/comments/img"}'
            result = json.loads(tool.execute(
                action="create_post", account="rd-main",
                subreddit="pics", post_type="image",
                title="Nice pic", image_path="/tmp/img.png",
            ))
        assert "url" in result

    def test_create_image_post_missing_path(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(
            action="create_post", account="rd-main",
            subreddit="pics", post_type="image",
        ))
        assert "image_path is required" in result["error"]

    def test_create_poll(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"url": "https://reddit.com/r/test/comments/poll"}'
            result = json.loads(tool.execute(
                action="create_post", account="rd-main",
                subreddit="test", post_type="poll",
                content="What's best?", options=["A", "B", "C"],
            ))
        assert "url" in result

    def test_create_poll_too_few_options(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(
            action="create_post", account="rd-main",
            subreddit="test", post_type="poll",
            content="Q?", options=["Only one"],
        ))
        assert "At least 2" in result["error"]

    def test_create_crosspost(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"url": "https://reddit.com/r/other/comments/xpost"}'
            result = json.loads(tool.execute(
                action="create_post", account="rd-main",
                subreddit="other", post_type="crosspost",
                post_url="https://reddit.com/r/test/comments/abc/original",
            ))
        assert "url" in result

    def test_create_crosspost_missing_url(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(
            action="create_post", account="rd-main",
            subreddit="other", post_type="crosspost",
        ))
        assert "post_url is required" in result["error"]

    def test_delete_post(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"deleted": true}'
            result = json.loads(tool.execute(
                action="delete_post", account="rd-main",
                post_url="https://reddit.com/r/test/comments/abc/post",
            ))
        assert result["deleted"] is True

    def test_delete_post_missing_url(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(action="delete_post", account="rd-main"))
        assert "error" in result


class TestMessagingActions:
    def test_send_message(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"sent": true}'
            result = json.loads(tool.execute(
                action="send_message", account="rd-main",
                recipient="someuser", message="Hello!",
            ))
        assert result["sent"] is True

    def test_send_message_missing_fields(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(
            action="send_message", account="rd-main",
        ))
        assert "error" in result

    def test_read_inbox(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"messages": [{"sender": "user1", "body": "Hi"}]}'
            result = json.loads(tool.execute(
                action="read_inbox", account="rd-main",
            ))
        assert "messages" in result


class TestSubredditActions:
    def test_join_subreddit(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"joined": true, "subreddit": "python"}'
            result = json.loads(tool.execute(
                action="join_subreddit", account="rd-main", subreddit="python",
            ))
        assert result["joined"] is True

    def test_join_subreddit_missing(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(action="join_subreddit", account="rd-main"))
        assert "error" in result

    def test_leave_subreddit(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"left": true, "subreddit": "python"}'
            result = json.loads(tool.execute(
                action="leave_subreddit", account="rd-main", subreddit="python",
            ))
        assert result["left"] is True

    def test_leave_subreddit_missing(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(action="leave_subreddit", account="rd-main"))
        assert "error" in result

    def test_list_subreddits(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"subreddits": [{"name": "python", "members": 1000000}]}'
            result = json.loads(tool.execute(
                action="list_subreddits", account="rd-main",
            ))
        assert "subreddits" in result


class TestAnalyticsActions:
    def test_get_post_performance(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"upvotes": 42, "comments": 5}'
            result = json.loads(tool.execute(
                action="get_post_performance", account="rd-main",
                post_url="https://reddit.com/r/test/comments/abc/post",
            ))
        assert result["upvotes"] == 42

    def test_get_post_performance_missing_url(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(
            action="get_post_performance", account="rd-main",
        ))
        assert "error" in result

    def test_get_karma(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = json.dumps({
                "post_karma": 1000, "comment_karma": 500,
                "total_karma": 1500, "account_age_days": 365,
            })
            result = json.loads(tool.execute(
                action="get_karma", account="rd-main",
            ))
        assert result["post_karma"] == 1000
        mock_store.record_reddit_profile_metrics.assert_called_once()

    def test_get_analytics_report_no_data(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        mock_store.get_reddit_profile_metrics_history.return_value = []
        result = json.loads(tool.execute(
            action="get_analytics_report", account="rd-main",
        ))
        assert "No Reddit profile metrics" in result["report"]

    def test_get_analytics_report_with_data(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        mock_store.get_reddit_profile_metrics_history.return_value = [
            {"post_karma": 500, "comment_karma": 200, "total_karma": 700,
             "account_age_days": 300, "recorded_at": "2026-02-01"},
            {"post_karma": 1000, "comment_karma": 500, "total_karma": 1500,
             "account_age_days": 330, "recorded_at": "2026-03-01"},
        ]
        result = json.loads(tool.execute(
            action="get_analytics_report", account="rd-main", days=30,
        ))
        report = result["report"]
        assert report["data_points"] == 2
        assert report["latest"]["total_karma"] == 1500
        assert report["growth"]["total_karma_change"] == 800


class TestDraftActions:
    def test_save_draft(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        mock_store.create_draft.return_value = 7
        result = json.loads(tool.execute(
            action="save_draft", account="rd-main", content="Draft post",
        ))
        assert result["saved"] is True
        assert result["draft_id"] == 7

    def test_save_draft_missing_content(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(action="save_draft", account="rd-main"))
        assert "error" in result

    def test_list_drafts(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        mock_store.list_drafts.return_value = [{"id": 1, "content": "draft"}]
        result = json.loads(tool.execute(action="list_drafts", account="rd-main"))
        assert result["count"] == 1

    def test_publish_draft(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        mock_store.get_draft.return_value = {
            "id": 7, "post_type": "text", "content": "Draft!",
            "title": "My Post", "metadata": {},
        }
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"url": "https://reddit.com/r/test/comments/new"}'
            result = json.loads(tool.execute(
                action="publish_draft", account="rd-main",
                draft_id=7, subreddit="test",
            ))
        assert "url" in result
        mock_store.delete_draft.assert_called_with(7)

    def test_publish_draft_not_found(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        mock_store.get_draft.return_value = None
        result = json.loads(tool.execute(
            action="publish_draft", account="rd-main",
            draft_id=999, subreddit="test",
        ))
        assert "not found" in result["error"]

    def test_publish_draft_missing_subreddit(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        mock_store.get_draft.return_value = {
            "id": 7, "post_type": "text", "content": "Draft!",
            "title": None, "metadata": {},
        }
        result = json.loads(tool.execute(
            action="publish_draft", account="rd-main", draft_id=7,
        ))
        assert "subreddit is required" in result["error"]


class TestKnowledgeActions:
    def test_explore_platform(self, tool, mock_store, mock_knowledge, reddit_account):
        mock_store.get_account.return_value = reddit_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = json.dumps({
                "observations": [
                    {"key": "feed_layout", "value": "card-based", "confidence": 0.9},
                ],
            })
            result = json.loads(tool.execute(
                action="explore_platform", account="rd-main", area="feed",
            ))
        assert "observations" in result
        mock_knowledge.record_learning.assert_called_once_with(
            platform="reddit",
            key="feed_layout",
            value="card-based",
            confidence=0.9,
        )

    def test_record_learning(self, tool, mock_store, mock_knowledge, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(
            action="record_learning", account="rd-main",
            key="upvote_color", value="orange",
        ))
        assert result["recorded"] is True
        mock_knowledge.record_learning.assert_called_once()

    def test_record_learning_missing_fields(self, tool, mock_store, reddit_account):
        mock_store.get_account.return_value = reddit_account
        result = json.loads(tool.execute(
            action="record_learning", account="rd-main", key="only_key",
        ))
        assert "error" in result


class TestCreateAccount:
    def test_create_account_missing_params(self, tool):
        result = json.loads(tool.execute(
            action="create_account", username="testuser",
        ))
        assert "error" in result
        assert "required" in result["error"]

    def test_create_account_no_email_store(self, tool_no_email):
        result = json.loads(tool_no_email.execute(
            action="create_account",
            username="testuser", password="pass123",
            email_account="work",
        ))
        assert "No email store" in result["error"]

    def test_create_account_email_not_found(self, tool, mock_email_store):
        mock_email_store.get.return_value = None
        result = json.loads(tool.execute(
            action="create_account",
            username="testuser", password="pass123",
            email_account="nonexistent",
        ))
        assert "not found" in result["error"]

    def test_create_account_success(self, tool, mock_store, mock_email_store):
        mock_email_store.get.return_value = {
            "email_address": "test@example.com",
            "password": "email-pass",
            "imap_host": "imap.example.com",
            "imap_port": 993,
        }
        mock_store.add_account.return_value = 42
        with patch.object(tool, "_exec_browser") as mock_browser:
            mock_browser.return_value = '{"success": true}'
            result = json.loads(tool.execute(
                action="create_account",
                username="testuser", password="pass123",
                email_account="work",
            ))
        assert result["created"] is True
        assert result["account_name"] == "rd-testuser"
        assert result["account_id"] == 42
        mock_store.add_account.assert_called_once_with(
            name="rd-testuser",
            platform="reddit",
            credentials={"username": "testuser", "password": "pass123"},
            config={"email_account": "work"},
        )

    def test_create_account_phone_required(self, tool, mock_email_store):
        mock_email_store.get.return_value = {
            "email_address": "test@example.com",
            "password": "email-pass",
            "imap_host": "imap.example.com",
            "imap_port": 993,
        }
        with patch.object(tool, "_exec_browser") as mock_browser:
            mock_browser.return_value = '{"error": "phone_verification_required"}'
            result = json.loads(tool.execute(
                action="create_account",
                username="testuser", password="pass123",
                email_account="work",
            ))
        assert result["error"] == "phone_verification_required"


class TestSessionPersistence:
    def test_browser_config_uses_profile_dir(self, tool, mock_store, reddit_account, tmp_path):
        mock_store.get_account.return_value = reddit_account
        with patch("src.tools.reddit.asyncio.run") as mock_run:
            mock_run.return_value = '{"posts": []}'
            tool.execute(
                action="browse_feed", account="rd-main",
            )
            mock_run.assert_called_once()
            assert mock_run.called
