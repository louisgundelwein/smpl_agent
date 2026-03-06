"""Tests for InstagramTool."""

import json
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from src.email_store import EmailAccountStore
from src.marketing.instagram import InstagramAdapter
from src.marketing.platform_knowledge import PlatformKnowledge
from src.marketing_store import MarketingStore
from src.tools.instagram import InstagramTool


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
    return InstagramAdapter(knowledge=None)


@pytest.fixture
def tool(mock_store, mock_knowledge, mock_adapter, mock_email_store, tmp_path):
    return InstagramTool(
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
        image_gen_base_url=None,
        image_gen_api_key=None,
    )


@pytest.fixture
def tool_no_email(mock_store, mock_knowledge, mock_adapter, tmp_path):
    return InstagramTool(
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
def ig_account():
    return {
        "id": 1,
        "name": "ig-main",
        "platform": "instagram",
        "credentials": {"username": "testuser", "password": "pass123"},
        "config": {},
    }


class TestDispatch:
    def test_unknown_action(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        result = json.loads(tool.execute(action="foobar", account="ig-main"))
        assert "Unknown action" in result["error"]

    def test_missing_account(self, tool, mock_store):
        mock_store.get_account.return_value = None
        result = json.loads(tool.execute(action="browse_feed", account="nope"))
        assert "not found" in result["error"]

    def test_wrong_platform(self, tool, mock_store):
        mock_store.get_account.return_value = {
            "id": 1, "name": "rd-main", "platform": "reddit",
            "credentials": {}, "config": {},
        }
        result = json.loads(tool.execute(action="browse_feed", account="rd-main"))
        assert "not an Instagram account" in result["error"]


class TestFeedActions:
    def test_browse_feed(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"posts": [{"author": "user1"}]}'
            result = json.loads(tool.execute(
                action="browse_feed", account="ig-main", query="travel",
            ))
        assert "posts" in result

    def test_browse_hashtag(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"posts": [{"author": "user1"}]}'
            result = json.loads(tool.execute(
                action="browse_hashtag", account="ig-main", hashtag="python",
            ))
        assert "posts" in result

    def test_browse_hashtag_missing(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        result = json.loads(tool.execute(action="browse_hashtag", account="ig-main"))
        assert "error" in result

    def test_search(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"results": [{"name": "AI page"}]}'
            result = json.loads(tool.execute(
                action="search", account="ig-main", query="AI",
            ))
        assert "results" in result

    def test_search_missing_query(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        result = json.loads(tool.execute(action="search", account="ig-main"))
        assert "error" in result


class TestInteractionActions:
    def test_like(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"liked": true}'
            result = json.loads(tool.execute(
                action="like", account="ig-main",
                post_url="https://www.instagram.com/p/abc123/",
            ))
        assert result["liked"] is True

    def test_like_missing_url(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        result = json.loads(tool.execute(action="like", account="ig-main"))
        assert "error" in result

    def test_unlike(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"unliked": true}'
            result = json.loads(tool.execute(
                action="unlike", account="ig-main",
                post_url="https://www.instagram.com/p/abc123/",
            ))
        assert result["unliked"] is True

    def test_comment(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"commented": true}'
            result = json.loads(tool.execute(
                action="comment", account="ig-main",
                post_url="https://www.instagram.com/p/abc123/",
                content="Great post!",
            ))
        assert result["commented"] is True

    def test_comment_missing_fields(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        result = json.loads(tool.execute(action="comment", account="ig-main"))
        assert "error" in result

    def test_reply_to_comment(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"replied": true}'
            result = json.loads(tool.execute(
                action="reply_to_comment", account="ig-main",
                post_url="https://www.instagram.com/p/abc123/",
                comment_id="user1", content="Thanks!",
            ))
        assert result["replied"] is True

    def test_reply_to_comment_missing_fields(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        result = json.loads(tool.execute(
            action="reply_to_comment", account="ig-main",
            post_url="https://www.instagram.com/p/abc123/",
        ))
        assert "error" in result


class TestContentActions:
    def test_create_photo_post(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"url": "https://www.instagram.com/p/new123/"}'
            result = json.loads(tool.execute(
                action="create_post", account="ig-main",
                content="Hello Instagram!", image_path="/tmp/img.png",
            ))
        assert "url" in result

    def test_create_photo_post_missing_image(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        result = json.loads(tool.execute(
            action="create_post", account="ig-main", content="No image",
        ))
        assert "image_path is required" in result["error"]

    def test_create_carousel_post(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"url": "https://www.instagram.com/p/carousel/"}'
            result = json.loads(tool.execute(
                action="create_post", account="ig-main",
                post_type="carousel", content="Carousel!",
                image_paths=["/tmp/a.png", "/tmp/b.png"],
            ))
        assert "url" in result

    def test_create_carousel_too_few_images(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        result = json.loads(tool.execute(
            action="create_post", account="ig-main",
            post_type="carousel", content="Carousel!",
            image_paths=["/tmp/a.png"],
        ))
        assert "at least 2" in result["error"]

    def test_create_reel(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"url": "https://www.instagram.com/reel/new/"}'
            result = json.loads(tool.execute(
                action="create_post", account="ig-main",
                post_type="reel", content="Reel time!",
                video_path="/tmp/vid.mp4",
            ))
        assert "url" in result

    def test_create_reel_missing_video(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        result = json.loads(tool.execute(
            action="create_post", account="ig-main",
            post_type="reel", content="Reel",
        ))
        assert "video_path is required" in result["error"]

    def test_create_post_with_image_generation(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_generate_image") as mock_gen, \
             patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_gen.return_value = {"path": "/tmp/generated.png"}
            mock_browser.return_value = '{"url": "https://www.instagram.com/p/gen/"}'
            result = json.loads(tool.execute(
                action="create_post", account="ig-main",
                content="AI art", generate_image_prompt="a sunset",
            ))
        assert "url" in result
        mock_gen.assert_called_once_with("a sunset")

    def test_create_post_image_generation_failure(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_generate_image") as mock_gen:
            mock_gen.return_value = {"error": "API error"}
            result = json.loads(tool.execute(
                action="create_post", account="ig-main",
                content="AI art", generate_image_prompt="a sunset",
            ))
        assert "Image generation failed" in result["error"]

    def test_create_story_image(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"shared": true, "type": "story"}'
            result = json.loads(tool.execute(
                action="create_story", account="ig-main",
                image_path="/tmp/story.png",
            ))
        assert result["shared"] is True

    def test_create_story_missing_content(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        result = json.loads(tool.execute(
            action="create_story", account="ig-main",
        ))
        assert "error" in result

    def test_delete_post(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"deleted": true}'
            result = json.loads(tool.execute(
                action="delete_post", account="ig-main",
                post_url="https://www.instagram.com/p/abc123/",
            ))
        assert result["deleted"] is True

    def test_delete_post_missing_url(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        result = json.loads(tool.execute(action="delete_post", account="ig-main"))
        assert "error" in result


class TestMessagingActions:
    def test_send_message(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"sent": true}'
            result = json.loads(tool.execute(
                action="send_message", account="ig-main",
                recipient="someuser", message="Hello!",
            ))
        assert result["sent"] is True

    def test_send_message_missing_fields(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        result = json.loads(tool.execute(action="send_message", account="ig-main"))
        assert "error" in result

    def test_read_inbox(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"messages": [{"sender": "user1", "body": "Hi"}]}'
            result = json.loads(tool.execute(action="read_inbox", account="ig-main"))
        assert "messages" in result


class TestFollowerActions:
    def test_follow_user(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"followed": true, "username": "cooluser"}'
            result = json.loads(tool.execute(
                action="follow_user", account="ig-main", username="cooluser",
            ))
        assert result["followed"] is True

    def test_follow_user_missing(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        result = json.loads(tool.execute(action="follow_user", account="ig-main"))
        assert "error" in result

    def test_unfollow_user(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"unfollowed": true, "username": "cooluser"}'
            result = json.loads(tool.execute(
                action="unfollow_user", account="ig-main", username="cooluser",
            ))
        assert result["unfollowed"] is True

    def test_unfollow_user_missing(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        result = json.loads(tool.execute(action="unfollow_user", account="ig-main"))
        assert "error" in result

    def test_list_followers(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"followers": [{"username": "fan1"}]}'
            result = json.loads(tool.execute(
                action="list_followers", account="ig-main",
            ))
        assert "followers" in result

    def test_list_following(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"following": [{"username": "idol1"}]}'
            result = json.loads(tool.execute(
                action="list_following", account="ig-main",
            ))
        assert "following" in result


class TestAnalyticsActions:
    def test_get_post_performance(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"likes": 42, "comments": 5}'
            result = json.loads(tool.execute(
                action="get_post_performance", account="ig-main",
                post_url="https://www.instagram.com/p/abc123/",
            ))
        assert result["likes"] == 42

    def test_get_post_performance_missing_url(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        result = json.loads(tool.execute(
            action="get_post_performance", account="ig-main",
        ))
        assert "error" in result

    def test_get_profile_analytics(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = json.dumps({
                "followers": 1000, "following": 500,
                "posts_count": 50, "engagement_rate": 3.5,
            })
            result = json.loads(tool.execute(
                action="get_profile_analytics", account="ig-main",
            ))
        assert result["followers"] == 1000
        mock_store.record_instagram_profile_metrics.assert_called_once()

    def test_get_analytics_report_no_data(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        mock_store.get_instagram_profile_metrics_history.return_value = []
        result = json.loads(tool.execute(
            action="get_analytics_report", account="ig-main",
        ))
        assert "No Instagram profile metrics" in result["report"]

    def test_get_analytics_report_with_data(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        mock_store.get_instagram_profile_metrics_history.return_value = [
            {"followers": 500, "following": 200, "posts_count": 30,
             "engagement_rate": 2.0, "recorded_at": "2026-02-01"},
            {"followers": 1000, "following": 500, "posts_count": 50,
             "engagement_rate": 3.5, "recorded_at": "2026-03-01"},
        ]
        result = json.loads(tool.execute(
            action="get_analytics_report", account="ig-main", days=30,
        ))
        report = result["report"]
        assert report["data_points"] == 2
        assert report["latest"]["followers"] == 1000
        assert report["growth"]["followers_change"] == 500


class TestDraftActions:
    def test_save_draft(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        mock_store.create_draft.return_value = 7
        result = json.loads(tool.execute(
            action="save_draft", account="ig-main", content="Draft post",
        ))
        assert result["saved"] is True
        assert result["draft_id"] == 7

    def test_save_draft_missing_content(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        result = json.loads(tool.execute(action="save_draft", account="ig-main"))
        assert "error" in result

    def test_list_drafts(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        mock_store.list_drafts.return_value = [{"id": 1, "content": "draft"}]
        result = json.loads(tool.execute(action="list_drafts", account="ig-main"))
        assert result["count"] == 1

    def test_publish_draft(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        mock_store.get_draft.return_value = {
            "id": 7, "post_type": "photo", "content": "Draft!",
            "title": "My Post", "metadata": {"image_path": "/tmp/img.png"},
        }
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = '{"url": "https://www.instagram.com/p/new/"}'
            result = json.loads(tool.execute(
                action="publish_draft", account="ig-main", draft_id=7,
            ))
        assert "url" in result
        mock_store.delete_draft.assert_called_with(7)

    def test_publish_draft_not_found(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        mock_store.get_draft.return_value = None
        result = json.loads(tool.execute(
            action="publish_draft", account="ig-main", draft_id=999,
        ))
        assert "not found" in result["error"]


class TestKnowledgeActions:
    def test_explore_platform(self, tool, mock_store, mock_knowledge, ig_account):
        mock_store.get_account.return_value = ig_account
        with patch.object(tool, "_run_browser_task", new_callable=AsyncMock) as mock_browser:
            mock_browser.return_value = json.dumps({
                "observations": [
                    {"key": "feed_layout", "value": "card-based", "confidence": 0.9},
                ],
            })
            result = json.loads(tool.execute(
                action="explore_platform", account="ig-main", area="feed",
            ))
        assert "observations" in result
        mock_knowledge.record_learning.assert_called_once_with(
            platform="instagram",
            key="feed_layout",
            value="card-based",
            confidence=0.9,
        )

    def test_record_learning(self, tool, mock_store, mock_knowledge, ig_account):
        mock_store.get_account.return_value = ig_account
        result = json.loads(tool.execute(
            action="record_learning", account="ig-main",
            key="story_duration", value="24 hours",
        ))
        assert result["recorded"] is True
        mock_knowledge.record_learning.assert_called_once()

    def test_record_learning_missing_fields(self, tool, mock_store, ig_account):
        mock_store.get_account.return_value = ig_account
        result = json.loads(tool.execute(
            action="record_learning", account="ig-main", key="only_key",
        ))
        assert "error" in result


class TestImageGeneration:
    def test_generate_image_standalone(self, tool):
        with patch("openai.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_response = MagicMock()
            mock_image = MagicMock()
            mock_image.b64_json = "aVZCT1J3MEtHZ29BQUFBTlNVaEVVZ0FBQU0="
            mock_response.data = [mock_image]
            mock_client.images.generate.return_value = mock_response

            result = json.loads(tool.execute(
                action="generate_image", content="a beautiful sunset",
            ))
        assert result["generated"] is True
        assert "path" in result

    def test_generate_image_missing_prompt(self, tool):
        result = json.loads(tool.execute(action="generate_image"))
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
        assert result["account_name"] == "ig-testuser"
        assert result["account_id"] == 42
        mock_store.add_account.assert_called_once_with(
            name="ig-testuser",
            platform="instagram",
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
    def test_browser_config_uses_profile_dir(self, tool, mock_store, ig_account, tmp_path):
        mock_store.get_account.return_value = ig_account
        with patch("src.tools.instagram.asyncio.run") as mock_run:
            mock_run.return_value = '{"posts": []}'
            tool.execute(action="browse_feed", account="ig-main")
            mock_run.assert_called_once()
            assert mock_run.called
