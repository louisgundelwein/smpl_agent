"""Twitter/X platform adapter."""

from typing import Any

from src.marketing.base import BrowserTask, PlatformAdapter


class TwitterAdapter(PlatformAdapter):
    """Generates browser task descriptions for Twitter/X."""

    @property
    def platform_name(self) -> str:
        return "twitter"

    def build_post_task(
        self,
        credentials: dict[str, Any],
        content: str,
        title: str | None = None,
        image_path: str | None = None,
        **kwargs: Any,
    ) -> BrowserTask:
        username = credentials["username"]
        password = credentials["password"]

        task = (
            f"Go to x.com and log in with username '{username}' and "
            f"password '{password}'. "
            "Click the compose/post button. "
        )
        # Twitter doesn't have titles; combine title + content if both provided
        text = f"{title}\n\n{content}" if title else content
        task += f"Type this text: '{text}'. "
        if image_path:
            task += f"Upload the image from '{image_path}'. "
        if kwargs.get("url"):
            task += f"Make sure the link {kwargs['url']} is included in the text. "
        task += (
            "Click 'Post' to publish. After posting, get the tweet URL. "
            'Return as JSON: {"url": "...", "post_id": "..."}.'
        )
        return BrowserTask(task_description=task, start_url="https://x.com")

    def build_metrics_task(
        self,
        credentials: dict[str, Any],
        platform_post_id: str,
    ) -> BrowserTask:
        task = (
            f"Go to x.com and log in with username '{credentials['username']}' "
            f"and password '{credentials['password']}'. "
            f"Navigate to the tweet at: {platform_post_id}. "
            "Read the current likes, retweets, replies, and views. "
            'Return as JSON: {"likes": N, "comments": N, "shares": N, '
            '"views": N, "extra": {"retweets": N, "bookmarks": N}}.'
        )
        return BrowserTask(task_description=task, start_url=platform_post_id)

    def build_get_comments_task(
        self,
        credentials: dict[str, Any],
        platform_post_id: str,
        limit: int = 20,
    ) -> BrowserTask:
        task = (
            f"Go to the tweet at: {platform_post_id}. "
            f"Read the top {limit} replies. For each reply, extract the "
            "author handle, text, and tweet ID. "
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
            f"Go to x.com and log in with username '{credentials['username']}' "
            f"and password '{credentials['password']}'. "
            f"Navigate to the reply at: {comment_id}. "
            f"Click the reply button. Type this reply: '{body}'. "
            "Click 'Reply' to submit. "
            'Return as JSON: {"replied": true, "comment_id": "..."}.'
        )
        return BrowserTask(task_description=task, start_url=comment_id)

    def build_delete_task(
        self,
        credentials: dict[str, Any],
        platform_post_id: str,
    ) -> BrowserTask:
        task = (
            f"Go to x.com and log in with username '{credentials['username']}' "
            f"and password '{credentials['password']}'. "
            f"Navigate to the tweet at: {platform_post_id}. "
            "Click the '...' menu, then click 'Delete'. Confirm deletion. "
            'Return as JSON: {"deleted": true}.'
        )
        return BrowserTask(task_description=task, start_url=platform_post_id)
