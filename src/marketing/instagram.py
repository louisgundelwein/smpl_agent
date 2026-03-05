"""Instagram platform adapter."""

from typing import Any

from src.marketing.base import BrowserTask, PlatformAdapter


class InstagramAdapter(PlatformAdapter):
    """Generates browser task descriptions for Instagram."""

    @property
    def platform_name(self) -> str:
        return "instagram"

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
            f"Go to instagram.com and log in with username '{username}' and "
            f"password '{password}'. "
        )
        if image_path:
            task += (
                "Click the '+' (create) button. "
                f"Upload the image from '{image_path}'. "
                "Click 'Next' through any editing screens. "
            )
        else:
            task += "Click the '+' (create) button. "
        caption = f"{title}\n\n{content}" if title else content
        task += f"Set the caption to: '{caption}'. "
        if kwargs.get("url"):
            task += f"Include the link {kwargs['url']} in the caption. "
        task += (
            "Click 'Share' to publish. After posting, get the post URL. "
            'Return as JSON: {"url": "...", "post_id": "..."}.'
        )
        return BrowserTask(task_description=task, start_url="https://www.instagram.com")

    def build_metrics_task(
        self,
        credentials: dict[str, Any],
        platform_post_id: str,
    ) -> BrowserTask:
        task = (
            f"Go to instagram.com and log in with username '{credentials['username']}' "
            f"and password '{credentials['password']}'. "
            f"Navigate to the post at: {platform_post_id}. "
            "Read the current likes and comment count. "
            'Return as JSON: {"likes": N, "comments": N, "shares": 0, '
            '"views": 0, "extra": {}}.'
        )
        return BrowserTask(task_description=task, start_url=platform_post_id)

    def build_get_comments_task(
        self,
        credentials: dict[str, Any],
        platform_post_id: str,
        limit: int = 20,
    ) -> BrowserTask:
        task = (
            f"Go to the Instagram post at: {platform_post_id}. "
            f"Read the top {limit} comments. For each comment, extract the "
            "author username, text, and any available identifier. "
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
            f"Go to instagram.com and log in with username '{credentials['username']}' "
            f"and password '{credentials['password']}'. "
            f"Navigate to the post at: {platform_post_id}. "
            f"Find the comment by '{comment_id}'. Click 'Reply'. "
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
            f"Go to instagram.com and log in with username '{credentials['username']}' "
            f"and password '{credentials['password']}'. "
            f"Navigate to the post at: {platform_post_id}. "
            "Click the '...' menu on the post, then click 'Delete'. "
            "Confirm deletion. "
            'Return as JSON: {"deleted": true}.'
        )
        return BrowserTask(task_description=task, start_url=platform_post_id)
