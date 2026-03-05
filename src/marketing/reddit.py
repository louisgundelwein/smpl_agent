"""Reddit platform adapter."""

from typing import Any

from src.marketing.base import BrowserTask, PlatformAdapter


class RedditAdapter(PlatformAdapter):
    """Generates browser task descriptions for Reddit."""

    @property
    def platform_name(self) -> str:
        return "reddit"

    def build_post_task(
        self,
        credentials: dict[str, Any],
        content: str,
        title: str | None = None,
        image_path: str | None = None,
        **kwargs: Any,
    ) -> BrowserTask:
        subreddit = kwargs.get("subreddit", "test")
        username = credentials["username"]
        password = credentials["password"]

        task = (
            f"Go to reddit.com and log in with username '{username}' and "
            f"password '{password}'. Then navigate to r/{subreddit}. "
            f"Click 'Create Post'. "
        )
        if title:
            task += f"Set the title to: '{title}'. "
        if image_path:
            task += f"Upload the image from '{image_path}'. "
        else:
            task += f"Set the body text to: '{content}'. "
        if kwargs.get("url"):
            task += f"Include the link: {kwargs['url']}. "
        task += (
            "Submit the post. After posting, return the post URL and ID. "
            'Return the result as JSON: {"url": "...", "post_id": "..."}.'
        )
        return BrowserTask(task_description=task, start_url="https://www.reddit.com")

    def build_metrics_task(
        self,
        credentials: dict[str, Any],
        platform_post_id: str,
    ) -> BrowserTask:
        task = (
            f"Go to reddit.com and log in with username '{credentials['username']}' "
            f"and password '{credentials['password']}'. "
            f"Navigate to the post at: {platform_post_id}. "
            "Read the current upvotes, comment count, and upvote ratio. "
            'Return as JSON: {"likes": N, "comments": N, "shares": 0, '
            '"views": 0, "extra": {"upvote_ratio": N}}.'
        )
        return BrowserTask(task_description=task, start_url=platform_post_id)

    def build_get_comments_task(
        self,
        credentials: dict[str, Any],
        platform_post_id: str,
        limit: int = 20,
    ) -> BrowserTask:
        task = (
            f"Go to the Reddit post at: {platform_post_id}. "
            f"Read the top {limit} comments. For each comment, extract the "
            "author, text, and comment ID. "
            'Return as JSON: {"comments": [{"id": "...", "author": "...", "text": "..."}]}.'
        )
        return BrowserTask(task_description=task, start_url=platform_post_id)

    def build_reply_task(
        self,
        credentials: dict[str, Any],
        platform_post_id: str,
        comment_id: str,
        body: str,
    ) -> BrowserTask:
        task = (
            f"Go to reddit.com and log in with username '{credentials['username']}' "
            f"and password '{credentials['password']}'. "
            f"Navigate to the post at: {platform_post_id}. "
            f"Find the comment with ID '{comment_id}'. Click reply. "
            f"Type this reply: '{body}'. Submit the reply. "
            'Return as JSON: {"replied": true, "comment_id": "..."}.'
        )
        return BrowserTask(task_description=task, start_url=platform_post_id)

    def build_delete_task(
        self,
        credentials: dict[str, Any],
        platform_post_id: str,
    ) -> BrowserTask:
        task = (
            f"Go to reddit.com and log in with username '{credentials['username']}' "
            f"and password '{credentials['password']}'. "
            f"Navigate to the post at: {platform_post_id}. "
            "Click the '...' menu, then click 'Delete'. Confirm deletion. "
            'Return as JSON: {"deleted": true}.'
        )
        return BrowserTask(task_description=task, start_url=platform_post_id)
