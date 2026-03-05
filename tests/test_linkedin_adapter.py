"""Tests for LinkedInAdapter."""

import pytest

from src.marketing.base import BrowserTask
from src.marketing.linkedin import LinkedInAdapter


@pytest.fixture
def adapter():
    """LinkedInAdapter without knowledge (no DB dependency)."""
    return LinkedInAdapter(knowledge=None)


@pytest.fixture
def creds():
    return {"username": "user@example.com", "password": "secret123"}


class TestCoreAdapterMethods:
    def test_platform_name(self, adapter):
        assert adapter.platform_name == "linkedin"

    def test_build_post_task(self, adapter, creds):
        task = adapter.build_post_task(creds, content="Hello world", title="My Post")
        assert isinstance(task, BrowserTask)
        assert "Hello world" in task.task_description
        assert "My Post" in task.task_description
        assert "linkedin.com" in task.start_url

    def test_build_post_task_with_image(self, adapter, creds):
        task = adapter.build_post_task(creds, content="pic", image_path="/tmp/img.png")
        assert "/tmp/img.png" in task.task_description

    def test_build_post_task_with_url(self, adapter, creds):
        task = adapter.build_post_task(creds, content="check", url="https://example.com")
        assert "https://example.com" in task.task_description

    def test_build_metrics_task(self, adapter, creds):
        task = adapter.build_metrics_task(creds, "https://linkedin.com/post/123")
        assert "reactions" in task.task_description
        assert task.start_url == "https://linkedin.com/post/123"

    def test_build_get_comments_task(self, adapter, creds):
        task = adapter.build_get_comments_task(creds, "https://linkedin.com/post/123", limit=5)
        assert "5" in task.task_description

    def test_build_reply_task(self, adapter, creds):
        task = adapter.build_reply_task(creds, "https://linkedin.com/post/123", "c1", "Thanks!")
        assert "Thanks!" in task.task_description
        assert "c1" in task.task_description

    def test_build_delete_task(self, adapter, creds):
        task = adapter.build_delete_task(creds, "https://linkedin.com/post/123")
        assert "Delete" in task.task_description


class TestFeedInteractions:
    def test_build_feed_browse_task(self, adapter, creds):
        task = adapter.build_feed_browse_task(creds, query="AI", limit=5)
        assert "AI" in task.task_description
        assert "5" in task.task_description

    def test_build_feed_browse_task_no_query(self, adapter, creds):
        task = adapter.build_feed_browse_task(creds)
        assert "home feed" in task.task_description

    def test_build_like_task(self, adapter, creds):
        task = adapter.build_like_task(creds, "https://linkedin.com/post/123")
        assert "Like" in task.task_description

    def test_build_comment_external_task(self, adapter, creds):
        task = adapter.build_comment_external_task(creds, "https://linkedin.com/post/123", "Great post!")
        assert "Great post!" in task.task_description

    def test_build_repost_task_with_commentary(self, adapter, creds):
        task = adapter.build_repost_task(creds, "https://linkedin.com/post/123", commentary="Must read!")
        assert "Must read!" in task.task_description
        assert "Repost with your thoughts" in task.task_description

    def test_build_repost_task_instant(self, adapter, creds):
        task = adapter.build_repost_task(creds, "https://linkedin.com/post/123")
        assert "instant repost" in task.task_description


class TestNetworking:
    def test_build_connection_request_task(self, adapter, creds):
        task = adapter.build_connection_request_task(
            creds, "https://linkedin.com/in/johndoe", note="Hi John!",
        )
        assert "Connect" in task.task_description
        assert "Hi John!" in task.task_description

    def test_build_connection_request_no_note(self, adapter, creds):
        task = adapter.build_connection_request_task(creds, "https://linkedin.com/in/johndoe")
        assert "Connect" in task.task_description
        assert "Add a note" not in task.task_description

    def test_build_accept_connections_task(self, adapter, creds):
        task = adapter.build_accept_connections_task(creds)
        assert "invitation-manager" in task.start_url
        assert "Accept" in task.task_description

    def test_build_send_message_task(self, adapter, creds):
        task = adapter.build_send_message_task(
            creds, "https://linkedin.com/in/johndoe", "Hello!",
        )
        assert "Hello!" in task.task_description
        assert "Message" in task.task_description

    def test_build_search_people_task(self, adapter, creds):
        task = adapter.build_search_people_task(
            creds, filters={"keywords": "engineer", "role": "CTO"},
        )
        assert "engineer" in task.task_description or "engineer" in task.start_url
        assert "CTO" in task.task_description or "CTO" in task.start_url

    def test_build_search_people_no_filters(self, adapter, creds):
        task = adapter.build_search_people_task(creds)
        assert "search/results/people" in task.start_url


class TestAdvancedContent:
    def test_build_article_task(self, adapter, creds):
        task = adapter.build_article_task(creds, "My Article", "Article body here")
        assert "My Article" in task.task_description
        assert "Article body here" in task.task_description
        assert "pulse" in task.start_url

    def test_build_carousel_task(self, adapter, creds):
        task = adapter.build_carousel_task(creds, "Carousel text", "/tmp/slides.pdf")
        assert "/tmp/slides.pdf" in task.task_description
        assert "document" in task.task_description.lower()

    def test_build_poll_task(self, adapter, creds):
        task = adapter.build_poll_task(creds, "What's best?", ["A", "B", "C"])
        assert "What's best?" in task.task_description
        assert "option 1" in task.task_description.lower()
        assert "'A'" in task.task_description
        assert "'B'" in task.task_description
        assert "'C'" in task.task_description


class TestSignup:
    def test_build_signup_task(self, adapter):
        task = adapter.build_signup_task(
            first_name="John",
            last_name="Doe",
            email_address="john@example.com",
            password="secret123",
            email_account_name="work",
        )
        assert isinstance(task, BrowserTask)
        assert "John" in task.task_description
        assert "Doe" in task.task_description
        assert "john@example.com" in task.task_description
        assert "secret123" in task.task_description
        assert "work" in task.task_description
        assert "signup" in task.start_url
        assert "Agree & Join" in task.task_description
        assert "phone_verification_required" in task.task_description


class TestAnalytics:
    def test_build_profile_analytics_task(self, adapter, creds):
        task = adapter.build_profile_analytics_task(creds)
        assert "dashboard" in task.start_url
        assert "profile_views" in task.task_description

    def test_build_ssi_score_task(self, adapter, creds):
        task = adapter.build_ssi_score_task(creds)
        assert "ssi" in task.start_url
        assert "ssi_score" in task.task_description
