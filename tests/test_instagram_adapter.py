"""Tests for InstagramAdapter."""

import pytest

from src.marketing.base import BrowserTask
from src.marketing.instagram import InstagramAdapter


@pytest.fixture
def adapter():
    """InstagramAdapter without knowledge (no DB dependency)."""
    return InstagramAdapter(knowledge=None)


@pytest.fixture
def creds():
    return {"username": "testuser", "password": "secret123"}


class TestCoreAdapterMethods:
    def test_platform_name(self, adapter):
        assert adapter.platform_name == "instagram"

    def test_build_post_task_photo(self, adapter, creds):
        task = adapter.build_post_task(
            creds, content="Hello world", title="My Post", image_path="/tmp/img.png",
        )
        assert isinstance(task, BrowserTask)
        assert "Hello world" in task.task_description
        assert "My Post" in task.task_description
        assert "/tmp/img.png" in task.task_description
        assert "instagram.com" in task.start_url

    def test_build_post_task_carousel(self, adapter, creds):
        task = adapter.build_post_task(
            creds, content="carousel", post_type="carousel",
            image_paths=["/tmp/a.png", "/tmp/b.png"],
        )
        assert "multi-select" in task.task_description
        assert "/tmp/a.png" in task.task_description
        assert "/tmp/b.png" in task.task_description

    def test_build_post_task_reel(self, adapter, creds):
        task = adapter.build_post_task(
            creds, content="reel", post_type="reel", video_path="/tmp/vid.mp4",
        )
        assert "Reel" in task.task_description
        assert "/tmp/vid.mp4" in task.task_description

    def test_build_post_task_with_location(self, adapter, creds):
        task = adapter.build_post_task(
            creds, content="post", image_path="/tmp/img.png", location="New York",
        )
        assert "New York" in task.task_description

    def test_build_metrics_task(self, adapter, creds):
        task = adapter.build_metrics_task(creds, "https://www.instagram.com/p/abc123/")
        assert "likes" in task.task_description
        assert task.start_url == "https://www.instagram.com/p/abc123/"

    def test_build_get_comments_task(self, adapter, creds):
        task = adapter.build_get_comments_task(
            creds, "https://www.instagram.com/p/abc123/", limit=5,
        )
        assert "5" in task.task_description

    def test_build_reply_task(self, adapter, creds):
        task = adapter.build_reply_task(
            creds, "https://www.instagram.com/p/abc123/", "user1", "Thanks!",
        )
        assert "Thanks!" in task.task_description
        assert "user1" in task.task_description

    def test_build_delete_task(self, adapter, creds):
        task = adapter.build_delete_task(creds, "https://www.instagram.com/p/abc123/")
        assert "Delete" in task.task_description


class TestStories:
    def test_build_story_task_image(self, adapter, creds):
        task = adapter.build_story_task(creds, image_path="/tmp/story.png")
        assert "/tmp/story.png" in task.task_description
        assert "Story" in task.task_description

    def test_build_story_task_video(self, adapter, creds):
        task = adapter.build_story_task(creds, video_path="/tmp/story.mp4")
        assert "/tmp/story.mp4" in task.task_description

    def test_build_story_task_text(self, adapter, creds):
        task = adapter.build_story_task(creds, text="Hello story!")
        assert "Hello story!" in task.task_description


class TestFeedBrowsing:
    def test_build_feed_browse_task(self, adapter, creds):
        task = adapter.build_feed_browse_task(creds, query="AI", limit=5)
        assert "AI" in task.task_description
        assert "5" in task.task_description

    def test_build_feed_browse_task_no_query(self, adapter, creds):
        task = adapter.build_feed_browse_task(creds)
        assert "home feed" in task.task_description

    def test_build_hashtag_browse_task(self, adapter, creds):
        task = adapter.build_hashtag_browse_task(creds, "#python", limit=5)
        assert "python" in task.task_description
        assert "tags/python" in task.start_url

    def test_build_hashtag_browse_task_no_hash(self, adapter, creds):
        task = adapter.build_hashtag_browse_task(creds, "travel")
        assert "tags/travel" in task.start_url

    def test_build_search_task(self, adapter, creds):
        task = adapter.build_search_task(creds, "machine learning")
        assert "machine learning" in task.task_description
        assert "explore" in task.start_url


class TestInteractions:
    def test_build_like_task(self, adapter, creds):
        task = adapter.build_like_task(creds, "https://www.instagram.com/p/abc123/")
        assert "heart" in task.task_description
        assert "like" in task.task_description.lower()

    def test_build_unlike_task(self, adapter, creds):
        task = adapter.build_unlike_task(creds, "https://www.instagram.com/p/abc123/")
        assert "unlike" in task.task_description.lower()

    def test_build_comment_task(self, adapter, creds):
        task = adapter.build_comment_task(
            creds, "https://www.instagram.com/p/abc123/", "Great post!",
        )
        assert "Great post!" in task.task_description


class TestMessaging:
    def test_build_send_message_task(self, adapter, creds):
        task = adapter.build_send_message_task(creds, "someuser", "Hello!")
        assert "Hello!" in task.task_description
        assert "someuser" in task.task_description
        assert "direct/inbox" in task.start_url

    def test_build_read_inbox_task(self, adapter, creds):
        task = adapter.build_read_inbox_task(creds, limit=5)
        assert "5" in task.task_description
        assert "direct/inbox" in task.start_url


class TestFollowers:
    def test_build_follow_task(self, adapter, creds):
        task = adapter.build_follow_task(creds, "cooluser")
        assert "Follow" in task.task_description
        assert "cooluser" in task.task_description
        assert "cooluser" in task.start_url

    def test_build_unfollow_task(self, adapter, creds):
        task = adapter.build_unfollow_task(creds, "cooluser")
        assert "Unfollow" in task.task_description
        assert "cooluser" in task.start_url

    def test_build_list_followers_task(self, adapter, creds):
        task = adapter.build_list_followers_task(creds, limit=20)
        assert "20" in task.task_description
        assert "followers" in task.task_description

    def test_build_list_following_task(self, adapter, creds):
        task = adapter.build_list_following_task(creds, limit=20)
        assert "20" in task.task_description
        assert "following" in task.task_description


class TestAnalytics:
    def test_build_profile_analytics_task(self, adapter, creds):
        task = adapter.build_profile_analytics_task(creds)
        assert "followers" in task.task_description.lower()
        assert "instagram.com" in task.start_url


class TestSignup:
    def test_build_signup_task(self, adapter):
        task = adapter.build_signup_task(
            username="testuser",
            password="secret123",
            email_address="test@example.com",
            email_account_name="work",
        )
        assert isinstance(task, BrowserTask)
        assert "testuser" in task.task_description
        assert "secret123" in task.task_description
        assert "test@example.com" in task.task_description
        assert "work" in task.task_description
        assert "emailsignup" in task.start_url
        assert "phone_verification_required" in task.task_description

    def test_build_signup_task_with_full_name(self, adapter):
        task = adapter.build_signup_task(
            username="testuser",
            password="secret123",
            email_address="test@example.com",
            email_account_name="work",
            full_name="Test User",
        )
        assert "Test User" in task.task_description
