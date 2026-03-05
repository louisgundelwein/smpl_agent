"""Tests for LinkedInTool."""

import json
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from src.marketing.linkedin import LinkedInAdapter
from src.marketing.platform_knowledge import PlatformKnowledge
from src.marketing_store import MarketingStore
from src.tools.linkedin import LinkedInTool


@pytest.fixture
def mock_store():
    return MagicMock(spec=MarketingStore)


@pytest.fixture
def mock_knowledge():
    k = MagicMock(spec=PlatformKnowledge)
    k.enhance_task.side_effect = lambda platform, task, context_keys=None: task
    k.get_guide.return_value = ""
    k.get_learnings.return_value = {}
    return k


@pytest.fixture
def mock_adapter(mock_knowledge):
    return LinkedInAdapter(knowledge=None)


@pytest.fixture
def tool(mock_store, mock_knowledge, mock_adapter):
    return LinkedInTool(
        store=mock_store,
        knowledge=mock_knowledge,
        adapter=mock_adapter,
        openai_api_key="test-key",
        openai_model="gpt-4o",
        openai_base_url=None,
        timeout=60,
        action_delay=0,
    )


@pytest.fixture
def linkedin_account():
    return {
        "id": 1,
        "name": "li-main",
        "platform": "linkedin",
        "credentials": {"username": "user@test.com", "password": "pass123"},
        "config": {},
    }


class TestDispatch:
    def test_unknown_action(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        result = json.loads(tool.execute(action="foobar", account="li-main"))
        assert "Unknown action" in result["error"]

    def test_missing_account(self, tool, mock_store):
        mock_store.get_account.return_value = None
        result = json.loads(tool.execute(action="browse_feed", account="nope"))
        assert "not found" in result["error"]

    def test_wrong_platform(self, tool, mock_store):
        mock_store.get_account.return_value = {
            "id": 1, "name": "reddit-main", "platform": "reddit",
            "credentials": {}, "config": {},
        }
        result = json.loads(tool.execute(action="browse_feed", account="reddit-main"))
        assert "not a LinkedIn account" in result["error"]


class TestFeedActions:
    def test_browse_feed(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"posts": [{"author": "John"}]}'
            result = json.loads(tool.execute(
                action="browse_feed", account="li-main", query="AI",
            ))
        assert "posts" in result

    def test_like_post(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"liked": true}'
            result = json.loads(tool.execute(
                action="like_post", account="li-main",
                post_url="https://linkedin.com/post/123",
            ))
        assert result["liked"] is True

    def test_like_post_missing_url(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        result = json.loads(tool.execute(action="like_post", account="li-main"))
        assert "error" in result

    def test_comment_post(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"commented": true}'
            result = json.loads(tool.execute(
                action="comment_post", account="li-main",
                post_url="https://linkedin.com/post/123",
                content="Great post!",
            ))
        assert result["commented"] is True

    def test_repost(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"reposted": true}'
            result = json.loads(tool.execute(
                action="repost", account="li-main",
                post_url="https://linkedin.com/post/123",
            ))
        assert result["reposted"] is True


class TestNetworkingActions:
    def test_send_connection(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"sent": true}'
            result = json.loads(tool.execute(
                action="send_connection", account="li-main",
                profile_url="https://linkedin.com/in/johndoe",
                note="Hi!",
            ))
        assert result["sent"] is True

    def test_send_connection_missing_url(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        result = json.loads(tool.execute(
            action="send_connection", account="li-main",
        ))
        assert "error" in result

    def test_accept_connections(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"accepted": 3}'
            result = json.loads(tool.execute(
                action="accept_connections", account="li-main",
            ))
        assert result["accepted"] == 3

    def test_send_message(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"sent": true}'
            result = json.loads(tool.execute(
                action="send_message", account="li-main",
                profile_url="https://linkedin.com/in/jane",
                message="Hello!",
            ))
        assert result["sent"] is True

    def test_send_message_missing_fields(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        result = json.loads(tool.execute(
            action="send_message", account="li-main",
        ))
        assert "error" in result

    def test_search_people(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"profiles": [{"name": "Jane"}]}'
            result = json.loads(tool.execute(
                action="search_people", account="li-main",
                filters={"keywords": "engineer"},
            ))
        assert "profiles" in result


class TestContentActions:
    def test_create_post(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"url": "https://linkedin.com/post/new"}'
            result = json.loads(tool.execute(
                action="create_post", account="li-main",
                content="Hello LinkedIn!",
            ))
        assert "url" in result

    def test_create_post_missing_content(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        result = json.loads(tool.execute(action="create_post", account="li-main"))
        assert "error" in result

    def test_create_article(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"url": "https://linkedin.com/pulse/..."}'
            result = json.loads(tool.execute(
                action="create_article", account="li-main",
                title="My Article", content="Article body",
            ))
        assert "url" in result

    def test_create_carousel(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"url": "https://linkedin.com/post/carousel"}'
            result = json.loads(tool.execute(
                action="create_carousel", account="li-main",
                content="Check out these slides", document_path="/tmp/deck.pdf",
            ))
        assert "url" in result

    def test_create_poll(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"url": "https://linkedin.com/post/poll"}'
            result = json.loads(tool.execute(
                action="create_poll", account="li-main",
                content="What's best?", options=["A", "B", "C"],
            ))
        assert "url" in result

    def test_create_poll_too_few_options(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        result = json.loads(tool.execute(
            action="create_poll", account="li-main",
            content="Q?", options=["Only one"],
        ))
        assert "At least 2" in result["error"]


class TestDraftActions:
    def test_save_draft(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        mock_store.create_draft.return_value = 7
        result = json.loads(tool.execute(
            action="save_draft", account="li-main", content="Draft post",
        ))
        assert result["saved"] is True
        assert result["draft_id"] == 7

    def test_list_drafts(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        mock_store.list_drafts.return_value = [{"id": 1, "content": "draft"}]
        result = json.loads(tool.execute(action="list_drafts", account="li-main"))
        assert result["count"] == 1

    def test_publish_draft(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        mock_store.get_draft.return_value = {
            "id": 7, "post_type": "text", "content": "Draft!", "title": None,
            "metadata": {},
        }
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"url": "https://linkedin.com/post/new"}'
            result = json.loads(tool.execute(
                action="publish_draft", account="li-main", draft_id=7,
            ))
        assert "url" in result
        mock_store.delete_draft.assert_called_with(7)

    def test_publish_draft_not_found(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        mock_store.get_draft.return_value = None
        result = json.loads(tool.execute(
            action="publish_draft", account="li-main", draft_id=999,
        ))
        assert "not found" in result["error"]


class TestAnalyticsActions:
    def test_get_profile_analytics(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = json.dumps({
                "profile_views": 100, "follower_count": 500,
                "connection_count": 200, "ssi_score": 70,
            })
            result = json.loads(tool.execute(
                action="get_profile_analytics", account="li-main",
            ))
        assert result["profile_views"] == 100
        mock_store.record_profile_metrics.assert_called_once()

    def test_get_post_performance(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"likes": 42, "comments": 5}'
            result = json.loads(tool.execute(
                action="get_post_performance", account="li-main",
                post_url="https://linkedin.com/post/123",
            ))
        assert result["likes"] == 42

    def test_get_ssi_score(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"ssi_score": 75}'
            result = json.loads(tool.execute(
                action="get_ssi_score", account="li-main",
            ))
        assert result["ssi_score"] == 75

    def test_get_analytics_report_no_data(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        mock_store.get_profile_metrics_history.return_value = []
        result = json.loads(tool.execute(
            action="get_analytics_report", account="li-main",
        ))
        assert "No profile metrics" in result["report"]

    def test_get_analytics_report_with_data(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        mock_store.get_profile_metrics_history.return_value = [
            {"profile_views": 50, "ssi_score": 60, "follower_count": 400,
             "connection_count": 150, "recorded_at": "2026-02-01"},
            {"profile_views": 100, "ssi_score": 70, "follower_count": 500,
             "connection_count": 200, "recorded_at": "2026-03-01"},
        ]
        result = json.loads(tool.execute(
            action="get_analytics_report", account="li-main", days=30,
        ))
        report = result["report"]
        assert report["data_points"] == 2
        assert report["latest"]["follower_count"] == 500
        assert report["growth"]["follower_change"] == 100


class TestKnowledgeActions:
    def test_explore_platform(self, tool, mock_store, mock_knowledge, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = json.dumps({
                "observations": [
                    {"key": "feed_layout", "value": "card-based", "confidence": 0.9},
                ],
            })
            result = json.loads(tool.execute(
                action="explore_platform", account="li-main", area="feed",
            ))
        assert "observations" in result
        mock_knowledge.record_learning.assert_called_once_with(
            platform="linkedin",
            key="feed_layout",
            value="card-based",
            confidence=0.9,
        )

    def test_record_learning(self, tool, mock_store, mock_knowledge, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        result = json.loads(tool.execute(
            action="record_learning", account="li-main",
            key="post_button_color", value="blue",
        ))
        assert result["recorded"] is True
        mock_knowledge.record_learning.assert_called_once()

    def test_record_learning_missing_fields(self, tool, mock_store, linkedin_account):
        mock_store.get_account.return_value = linkedin_account
        result = json.loads(tool.execute(
            action="record_learning", account="li-main", key="only_key",
        ))
        assert "error" in result
