"""Instagram platform adapter."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from src.marketing.base import BrowserTask, PlatformAdapter

if TYPE_CHECKING:
    from src.marketing.platform_knowledge import PlatformKnowledge


def _login_prefix(credentials: dict[str, Any]) -> str:
    return (
        f"Go to instagram.com and log in with username '{credentials['username']}' "
        f"and password '{credentials['password']}'. "
        "If a 'Save Your Login Info' prompt appears, click 'Not Now'. "
    )


class InstagramAdapter(PlatformAdapter):
    """Generates browser task descriptions for Instagram."""

    def __init__(self, knowledge: PlatformKnowledge | None = None) -> None:
        self._knowledge = knowledge

    @property
    def platform_name(self) -> str:
        return "instagram"

    def _enhance(self, task: BrowserTask, context_keys: list[str] | None = None) -> BrowserTask:
        if self._knowledge:
            return self._knowledge.enhance_task("instagram", task, context_keys)
        return task

    # ------------------------------------------------------------------
    # Core content
    # ------------------------------------------------------------------

    def build_post_task(
        self,
        credentials: dict[str, Any],
        content: str,
        title: str | None = None,
        image_path: str | None = None,
        **kwargs: Any,
    ) -> BrowserTask:
        post_type = kwargs.get("post_type", "photo")
        location = kwargs.get("location")
        image_paths = kwargs.get("image_paths")

        task = _login_prefix(credentials)
        task += "Click the '+' (create) icon in the top navigation. "

        if post_type == "reel":
            video_path = kwargs.get("video_path")
            task += "Select 'Reel' from the dropdown. "
            if video_path:
                task += f"Upload the video from '{video_path}'. "
            task += "Click 'Next' through any editing screens. "
        elif post_type == "carousel" and image_paths:
            task += "Select 'Post' from the dropdown. "
            task += "Click the multi-select icon (overlapping squares). "
            for i, path in enumerate(image_paths[:10], 1):
                task += f"Select image {i}: '{path}'. "
            task += "Click 'Next' through any editing screens. "
        else:
            task += "Select 'Post' from the dropdown. "
            if image_path:
                task += f"Upload the image from '{image_path}'. "
            task += "Click 'Next' through any editing screens. "

        caption = f"{title}\n\n{content}" if title else content
        task += f"Set the caption to: '{caption}'. "

        if location:
            task += f"Click 'Add location' and search for '{location}'. Select it. "

        task += (
            "Click 'Share' to publish. After posting, get the post URL. "
            'Return as JSON: {"url": "...", "post_id": "..."}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url="https://www.instagram.com"),
            context_keys=["post_creation"],
        )

    def build_metrics_task(
        self,
        credentials: dict[str, Any],
        platform_post_id: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to the post at: {platform_post_id}. "
            "Read the current likes and comment count. "
            'Return as JSON: {"likes": N, "comments": N, "shares": 0, '
            '"views": 0, "extra": {}}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url=platform_post_id),
            context_keys=["metrics_reading"],
        )

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
        return self._enhance(
            BrowserTask(task_description=task, start_url=platform_post_id),
            context_keys=["comments_section"],
        )

    def build_reply_task(
        self,
        credentials: dict[str, Any],
        platform_post_id: str,
        comment_id: str,
        body: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to the post at: {platform_post_id}. "
            f"Find the comment by '{comment_id}'. Click 'Reply'. "
            f"Type this reply: '{body}'. Submit the reply. "
            'Return as JSON: {"replied": true, "comment_id": "..."}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url=platform_post_id),
            context_keys=["comments_section", "reply_behavior"],
        )

    def build_delete_task(
        self,
        credentials: dict[str, Any],
        platform_post_id: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to the post at: {platform_post_id}. "
            "Click the '...' menu on the post, then click 'Delete'. "
            "Confirm deletion. "
            'Return as JSON: {"deleted": true}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url=platform_post_id),
            context_keys=["modal_behavior"],
        )

    # ------------------------------------------------------------------
    # Stories
    # ------------------------------------------------------------------

    def build_story_task(
        self,
        credentials: dict[str, Any],
        image_path: str | None = None,
        video_path: str | None = None,
        text: str | None = None,
    ) -> BrowserTask:
        task = _login_prefix(credentials)
        task += "Click the '+' (create) icon and select 'Story'. "

        if video_path:
            task += f"Upload the video from '{video_path}'. "
        elif image_path:
            task += f"Upload the image from '{image_path}'. "

        if text:
            task += f"Add text overlay: '{text}'. "

        task += (
            "Click 'Share to Story' or 'Your Story' to publish. "
            'Return as JSON: {"shared": true, "type": "story"}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url="https://www.instagram.com"),
            context_keys=["story_creation"],
        )

    # ------------------------------------------------------------------
    # Feed browsing
    # ------------------------------------------------------------------

    def build_feed_browse_task(
        self,
        credentials: dict[str, Any],
        query: str | None = None,
        limit: int = 10,
    ) -> BrowserTask:
        task = _login_prefix(credentials)
        if query:
            task += (
                f"Click the search icon and search for '{query}'. "
            )
        else:
            task += "Go to the Instagram home feed. "
        task += (
            f"Collect up to {limit} posts. "
            "For each post, extract: author username, caption preview, "
            "likes count, comments count, post URL. "
            'Return as JSON: {"posts": [{"author": "...", "caption": "...", '
            '"likes": N, "comments": N, "url": "..."}]}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url="https://www.instagram.com/"),
            context_keys=["feed_navigation"],
        )

    def build_hashtag_browse_task(
        self,
        credentials: dict[str, Any],
        hashtag: str,
        limit: int = 10,
    ) -> BrowserTask:
        clean = hashtag.lstrip("#")
        task = (
            _login_prefix(credentials)
            + f"Navigate to the hashtag page for #{clean}. "
            f"Collect up to {limit} posts from the top and recent sections. "
            "For each post, extract: author, caption preview, likes, comments, URL. "
            'Return as JSON: {"posts": [{"author": "...", "caption": "...", '
            '"likes": N, "comments": N, "url": "..."}]}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url=f"https://www.instagram.com/explore/tags/{clean}/",
            ),
            context_keys=["feed_navigation", "hashtag_browsing"],
        )

    def build_search_task(
        self,
        credentials: dict[str, Any],
        query: str,
        limit: int = 10,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Click the search icon. Search for '{query}'. "
            f"Collect up to {limit} results (accounts, tags, or places). "
            "For each result, extract: name, type (account/tag/place), URL. "
            'Return as JSON: {"results": [{"name": "...", "type": "...", "url": "..."}]}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url="https://www.instagram.com/explore/",
            ),
            context_keys=["search"],
        )

    # ------------------------------------------------------------------
    # Interactions
    # ------------------------------------------------------------------

    def build_like_task(
        self,
        credentials: dict[str, Any],
        post_url: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to the post at: {post_url}. "
            "Click the heart icon to like the post. "
            'Return as JSON: {"liked": true, "post_url": "..."}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url=post_url),
            context_keys=["liking"],
        )

    def build_unlike_task(
        self,
        credentials: dict[str, Any],
        post_url: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to the post at: {post_url}. "
            "If the heart icon is red (already liked), click it to unlike. "
            'Return as JSON: {"unliked": true, "post_url": "..."}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url=post_url),
            context_keys=["liking"],
        )

    def build_comment_task(
        self,
        credentials: dict[str, Any],
        post_url: str,
        text: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to the post at: {post_url}. "
            f"Type this comment: '{text}'. "
            "Click 'Post' to submit the comment. "
            'Return as JSON: {"commented": true, "post_url": "..."}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url=post_url),
            context_keys=["comments_section"],
        )

    # ------------------------------------------------------------------
    # DMs
    # ------------------------------------------------------------------

    def build_send_message_task(
        self,
        credentials: dict[str, Any],
        recipient: str,
        message: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + "Click the messenger/paper-plane icon to go to Direct Messages. "
            "Click the compose/new-message icon. "
            f"Search for and select user '{recipient}'. "
            f"Type this message: '{message}'. "
            "Press Enter or click 'Send'. "
            'Return as JSON: {"sent": true, "recipient": "..."}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url="https://www.instagram.com/direct/inbox/",
            ),
            context_keys=["messaging"],
        )

    def build_read_inbox_task(
        self,
        credentials: dict[str, Any],
        limit: int = 10,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + "Go to Direct Messages inbox. "
            f"Read up to {limit} conversations. For each, extract: sender, last message, date. "
            'Return as JSON: {"messages": [{"sender": "...", "body": "...", "date": "..."}]}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url="https://www.instagram.com/direct/inbox/",
            ),
            context_keys=["messaging"],
        )

    # ------------------------------------------------------------------
    # Followers
    # ------------------------------------------------------------------

    def build_follow_task(
        self,
        credentials: dict[str, Any],
        username: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to the profile of '{username}'. "
            "Click the 'Follow' button. "
            'Return as JSON: {"followed": true, "username": "..."}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url=f"https://www.instagram.com/{username}/",
            ),
            context_keys=["follow_management"],
        )

    def build_unfollow_task(
        self,
        credentials: dict[str, Any],
        username: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to the profile of '{username}'. "
            "Click the 'Following' button, then confirm 'Unfollow'. "
            'Return as JSON: {"unfollowed": true, "username": "..."}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url=f"https://www.instagram.com/{username}/",
            ),
            context_keys=["follow_management"],
        )

    def build_list_followers_task(
        self,
        credentials: dict[str, Any],
        limit: int = 50,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + "Go to your profile page. Click on the 'followers' count. "
            f"Read up to {limit} followers. For each, extract: username, full name. "
            'Return as JSON: {"followers": [{"username": "...", "name": "..."}]}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url="https://www.instagram.com/",
            ),
            context_keys=["follow_management"],
        )

    def build_list_following_task(
        self,
        credentials: dict[str, Any],
        limit: int = 50,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + "Go to your profile page. Click on the 'following' count. "
            f"Read up to {limit} accounts you follow. For each, extract: username, full name. "
            'Return as JSON: {"following": [{"username": "...", "name": "..."}]}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url="https://www.instagram.com/",
            ),
            context_keys=["follow_management"],
        )

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def build_profile_analytics_task(
        self,
        credentials: dict[str, Any],
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + "Go to your profile page. "
            "Read the followers count, following count, and posts count. "
            "If insights/professional dashboard is available, read engagement rate. "
            'Return as JSON: {"followers": N, "following": N, '
            '"posts_count": N, "engagement_rate": N}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url="https://www.instagram.com/",
            ),
            context_keys=["profile_analytics"],
        )

    # ------------------------------------------------------------------
    # Account creation
    # ------------------------------------------------------------------

    def build_signup_task(
        self,
        username: str,
        password: str,
        email_address: str,
        email_account_name: str,
        full_name: str | None = None,
    ) -> BrowserTask:
        task = (
            "Go to https://www.instagram.com/accounts/emailsignup/. "
            f"Enter the email '{email_address}'. "
        )
        if full_name:
            task += f"Enter full name '{full_name}'. "
        else:
            task += f"Enter full name '{username}'. "
        task += (
            f"Set the username to '{username}'. "
            f"Set the password to '{password}'. "
            "Click 'Sign up'. "
            "If an email verification code is requested, call the "
            f"read_verification_email action with email_account_name='{email_account_name}' "
            "to get the code, then enter it and click 'Confirm'. "
            "If a birthday prompt appears, enter a valid date (e.g. January 1, 1995) and click 'Next'. "
            "If a CAPTCHA appears, solve it visually. "
            "Skip any profile photo prompts by clicking 'Skip'. "
            "If a phone number is required and cannot be skipped (try 'Skip' or 'Not now' first), "
            'return {"error": "phone_verification_required"}. '
            'On success, return {"success": true}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url="https://www.instagram.com/accounts/emailsignup/",
            ),
            context_keys=["signup", "captcha_handling"],
        )
