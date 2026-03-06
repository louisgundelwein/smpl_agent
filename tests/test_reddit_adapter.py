"""Tests for RedditAdapter."""

import pytest

from src.marketing.base import BrowserTask
from src.marketing.reddit import RedditAdapter


@pytest.fixture
def adapter():
    """RedditAdapter without knowledge (no DB dependency)."""
    return RedditAdapter(knowledge=None)


@pytest.fixture
def creds():
    return {"username": "testuser", "password": "secret123"}


class TestCoreAdapterMethods:
    def test_platform_name(self, adapter):
        assert adapter.platform_name == "reddit"

    def test_build_post_task_text(self, adapter, creds):
        task = adapter.build_post_task(
            creds, content="Hello world", title="My Post", subreddit="test",
        )
        assert isinstance(task, BrowserTask)
        assert "Hello world" in task.task_description
        assert "My Post" in task.task_description
        assert "reddit.com" in task.start_url

    def test_build_post_task_with_image(self, adapter, creds):
        task = adapter.build_post_task(
            creds, content="pic", image_path="/tmp/img.png", subreddit="pics",
        )
        assert "/tmp/img.png" in task.task_description
        assert "Images" in task.task_description

    def test_build_post_task_with_url(self, adapter, creds):
        task = adapter.build_post_task(
            creds, content="check", url="https://example.com", subreddit="test",
        )
        assert "https://example.com" in task.task_description
        assert "Link" in task.task_description

    def test_build_post_task_with_flair(self, adapter, creds):
        task = adapter.build_post_task(
            creds, content="post", subreddit="test", flair="Discussion",
        )
        assert "Discussion" in task.task_description

    def test_build_metrics_task(self, adapter, creds):
        task = adapter.build_metrics_task(creds, "https://reddit.com/r/test/comments/abc/post")
        assert "upvotes" in task.task_description
        assert task.start_url == "https://reddit.com/r/test/comments/abc/post"

    def test_build_get_comments_task(self, adapter, creds):
        task = adapter.build_get_comments_task(
            creds, "https://reddit.com/r/test/comments/abc/post", limit=5,
        )
        assert "5" in task.task_description

    def test_build_reply_task(self, adapter, creds):
        task = adapter.build_reply_task(
            creds, "https://reddit.com/r/test/comments/abc/post", "c1", "Thanks!",
        )
        assert "Thanks!" in task.task_description
        assert "c1" in task.task_description

    def test_build_delete_task(self, adapter, creds):
        task = adapter.build_delete_task(creds, "https://reddit.com/r/test/comments/abc/post")
        assert "Delete" in task.task_description


class TestFeedBrowsing:
    def test_build_feed_browse_task(self, adapter, creds):
        task = adapter.build_feed_browse_task(creds, query="AI", limit=5, sort="new")
        assert "AI" in task.task_description
        assert "5" in task.task_description
        assert "new" in task.task_description

    def test_build_feed_browse_task_no_query(self, adapter, creds):
        task = adapter.build_feed_browse_task(creds)
        assert "home feed" in task.task_description

    def test_build_subreddit_browse_task(self, adapter, creds):
        task = adapter.build_subreddit_browse_task(creds, "python", limit=5, sort="top")
        assert "r/python" in task.task_description
        assert "top" in task.task_description
        assert "python" in task.start_url

    def test_build_search_task(self, adapter, creds):
        task = adapter.build_search_task(creds, "machine learning", subreddit="python")
        assert "machine learning" in task.task_description
        assert "r/python" in task.task_description
        assert "restrict_sr" in task.start_url

    def test_build_search_task_global(self, adapter, creds):
        task = adapter.build_search_task(creds, "AI tools")
        assert "AI tools" in task.task_description
        assert "search" in task.start_url


class TestVoting:
    def test_build_vote_task_upvote(self, adapter, creds):
        task = adapter.build_vote_task(creds, "https://reddit.com/r/test/comments/abc", direction="up")
        assert "upvote" in task.task_description

    def test_build_vote_task_downvote(self, adapter, creds):
        task = adapter.build_vote_task(creds, "https://reddit.com/r/test/comments/abc", direction="down")
        assert "downvote" in task.task_description


class TestComments:
    def test_build_comment_task(self, adapter, creds):
        task = adapter.build_comment_task(
            creds, "https://reddit.com/r/test/comments/abc", "Great post!",
        )
        assert "Great post!" in task.task_description
        assert "Comment" in task.task_description


class TestMessaging:
    def test_build_send_message_task(self, adapter, creds):
        task = adapter.build_send_message_task(creds, "someuser", "Hello!")
        assert "Hello!" in task.task_description
        assert "someuser" in task.task_description
        assert "message/compose" in task.start_url

    def test_build_read_inbox_task(self, adapter, creds):
        task = adapter.build_read_inbox_task(creds, limit=5)
        assert "5" in task.task_description
        assert "inbox" in task.start_url


class TestSubredditManagement:
    def test_build_join_subreddit_task(self, adapter, creds):
        task = adapter.build_join_subreddit_task(creds, "python")
        assert "Join" in task.task_description
        assert "r/python" in task.task_description

    def test_build_leave_subreddit_task(self, adapter, creds):
        task = adapter.build_leave_subreddit_task(creds, "python")
        assert "Leave" in task.task_description or "unsubscribe" in task.task_description
        assert "r/python" in task.task_description

    def test_build_list_subreddits_task(self, adapter, creds):
        task = adapter.build_list_subreddits_task(creds)
        assert "subreddits/mine" in task.start_url


class TestPolls:
    def test_build_poll_task(self, adapter, creds):
        task = adapter.build_poll_task(creds, "test", "What's best?", ["A", "B", "C"])
        assert "What's best?" in task.task_description
        assert "option 1" in task.task_description.lower()
        assert "'A'" in task.task_description
        assert "'B'" in task.task_description
        assert "'C'" in task.task_description
        assert "Poll" in task.task_description


class TestCrosspost:
    def test_build_crosspost_task(self, adapter, creds):
        task = adapter.build_crosspost_task(
            creds, "other", "https://reddit.com/r/test/comments/abc/original",
            title="Crosspost",
        )
        assert "Crosspost" in task.task_description
        assert "r/other" in task.task_description


class TestAnalytics:
    def test_build_karma_task(self, adapter, creds):
        task = adapter.build_karma_task(creds)
        assert "karma" in task.task_description.lower()
        assert "user/me" in task.start_url

    def test_build_profile_analytics_task(self, adapter, creds):
        task = adapter.build_profile_analytics_task(creds)
        assert "karma" in task.task_description.lower()
        assert "user/me" in task.start_url


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
        assert "register" in task.start_url
        assert "phone_verification_required" in task.task_description
