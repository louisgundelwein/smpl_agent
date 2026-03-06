"""Reddit platform adapter."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from src.marketing.base import BrowserTask, PlatformAdapter

if TYPE_CHECKING:
    from src.marketing.platform_knowledge import PlatformKnowledge


def _login_prefix(credentials: dict[str, Any]) -> str:
    return (
        f"Go to reddit.com and log in with username '{credentials['username']}' "
        f"and password '{credentials['password']}'. "
    )


class RedditAdapter(PlatformAdapter):
    """Generates browser task descriptions for Reddit."""

    def __init__(self, knowledge: PlatformKnowledge | None = None) -> None:
        self._knowledge = knowledge

    @property
    def platform_name(self) -> str:
        return "reddit"

    def _enhance(self, task: BrowserTask, context_keys: list[str] | None = None) -> BrowserTask:
        if self._knowledge:
            return self._knowledge.enhance_task("reddit", task, context_keys)
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
        subreddit = kwargs.get("subreddit", "test")
        task = _login_prefix(credentials)
        task += f"Navigate to r/{subreddit} submit page. "

        url = kwargs.get("url")
        flair = kwargs.get("flair")

        if image_path:
            task += "Select the 'Images & Video' tab. "
            if title:
                task += f"Set the title to: '{title}'. "
            task += f"Upload the image from '{image_path}'. "
            task += f"Body: '{content}'. "
        elif url:
            task += "Select the 'Link' tab. "
            if title:
                task += f"Set the title to: '{title}'. "
            task += f"Paste the URL: {url}. "
            task += f"Body: '{content}'. "
        else:
            task += "Select the 'Text' or 'Post' tab. "
            if title:
                task += f"Set the title to: '{title}'. "
            task += f"Set the body text to: '{content}'. "

        if flair:
            task += f"Select the flair '{flair}' from the flair dropdown. "

        task += (
            "Click 'Post' to submit. After posting, get the post URL. "
            'Return as JSON: {"url": "...", "post_id": "..."}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url="https://www.reddit.com"),
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
            "Read the current upvotes, comment count, and upvote ratio. "
            'Return as JSON: {"likes": N, "comments": N, "shares": 0, '
            '"views": 0, "extra": {"upvote_ratio": N}}.'
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
            f"Go to the Reddit post at: {platform_post_id}. "
            f"Read the top {limit} comments. For each comment, extract the "
            "author, text, and comment ID. "
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
            f"Find the comment with ID '{comment_id}'. Click reply. "
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
            "Click the '...' menu, then click 'Delete'. Confirm deletion. "
            'Return as JSON: {"deleted": true}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url=platform_post_id),
            context_keys=["modal_behavior"],
        )

    # ------------------------------------------------------------------
    # Feed browsing
    # ------------------------------------------------------------------

    def build_feed_browse_task(
        self,
        credentials: dict[str, Any],
        query: str | None = None,
        limit: int = 10,
        sort: str = "hot",
    ) -> BrowserTask:
        task = _login_prefix(credentials)
        if query:
            task += (
                f"Search Reddit for '{query}'. "
                f"Sort results by {sort}. "
            )
        else:
            task += "Go to the Reddit home feed. "
        task += (
            f"Collect up to {limit} posts. "
            "For each post, extract: title, author, subreddit, upvotes, "
            "comments count, post URL. "
            'Return as JSON: {"posts": [{"title": "...", "author": "...", '
            '"subreddit": "...", "upvotes": N, "comments": N, "url": "..."}]}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url="https://www.reddit.com/"),
            context_keys=["feed_navigation"],
        )

    def build_subreddit_browse_task(
        self,
        credentials: dict[str, Any],
        subreddit: str,
        limit: int = 10,
        sort: str = "hot",
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to r/{subreddit} and sort by {sort}. "
            f"Collect up to {limit} posts. "
            "For each post, extract: title, author, upvotes, comments count, URL. "
            'Return as JSON: {"posts": [{"title": "...", "author": "...", '
            '"upvotes": N, "comments": N, "url": "..."}]}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url=f"https://www.reddit.com/r/{subreddit}/{sort}/",
            ),
            context_keys=["feed_navigation", "subreddit_browsing"],
        )

    def build_search_task(
        self,
        credentials: dict[str, Any],
        query: str,
        subreddit: str | None = None,
        sort: str = "hot",
        limit: int = 10,
    ) -> BrowserTask:
        task = _login_prefix(credentials)
        if subreddit:
            task += f"Search for '{query}' within r/{subreddit}. "
            start_url = (
                f"https://www.reddit.com/r/{subreddit}/search/"
                f"?q={query}&restrict_sr=1"
            )
        else:
            task += f"Search Reddit for '{query}'. "
            start_url = f"https://www.reddit.com/search/?q={query}"

        task += (
            "Collect up to 10 results. For each, extract: title, author, "
            "subreddit, upvotes, comments count, URL. "
            'Return as JSON: {"posts": [...]}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url=start_url),
            context_keys=["search"],
        )

    # ------------------------------------------------------------------
    # Voting
    # ------------------------------------------------------------------

    def build_vote_task(
        self,
        credentials: dict[str, Any],
        post_url: str,
        direction: str = "up",
    ) -> BrowserTask:
        verb = "upvote" if direction == "up" else "downvote"
        task = (
            _login_prefix(credentials)
            + f"Navigate to the post at: {post_url}. "
            f"Click the {verb} button on the post. "
            f'Return as JSON: {{"{verb}d": true, "post_url": "..."}}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url=post_url),
            context_keys=["voting"],
        )

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    def build_comment_task(
        self,
        credentials: dict[str, Any],
        post_url: str,
        text: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to the post at: {post_url}. "
            "Comment on the post. "
            f"Type this comment: '{text}'. "
            "Click the submit button. "
            'Return as JSON: {"commented": true, "post_url": "..."}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url=post_url),
            context_keys=["comments_section"],
        )

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    def build_send_message_task(
        self,
        credentials: dict[str, Any],
        recipient: str,
        message: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Go to the message compose page for user '{recipient}'. "
            f"Type this message: '{message}'. "
            "Click 'Send'. "
            'Return as JSON: {"sent": true, "recipient": "..."}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url=f"https://www.reddit.com/message/compose/?to={recipient}",
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
            + "Go to the Reddit inbox. "
            f"Read up to {limit} messages. For each, extract: sender, subject, body, date. "
            'Return as JSON: {"messages": [{"sender": "...", "subject": "...", '
            '"body": "...", "date": "..."}]}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url="https://www.reddit.com/message/inbox/",
            ),
            context_keys=["messaging"],
        )

    # ------------------------------------------------------------------
    # Subreddit management
    # ------------------------------------------------------------------

    def build_join_subreddit_task(
        self,
        credentials: dict[str, Any],
        subreddit: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to r/{subreddit}. "
            f"Join the subreddit by clicking the 'Join' button. "
            'Return as JSON: {"joined": true, "subreddit": "..."}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url=f"https://www.reddit.com/r/{subreddit}/",
            ),
            context_keys=["subreddit_management"],
        )

    def build_leave_subreddit_task(
        self,
        credentials: dict[str, Any],
        subreddit: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to r/{subreddit}. "
            f"Leave or unsubscribe from the subreddit by clicking the 'Joined' button. "
            'Return as JSON: {"left": true, "subreddit": "..."}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url=f"https://www.reddit.com/r/{subreddit}/",
            ),
            context_keys=["subreddit_management"],
        )

    def build_list_subreddits_task(
        self,
        credentials: dict[str, Any],
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + "Go to the 'My Subreddits' page. "
            "List all subscribed subreddits with their member counts. "
            'Return as JSON: {"subreddits": [{"name": "...", "members": N}]}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url="https://www.reddit.com/subreddits/mine/",
            ),
            context_keys=["subreddit_management"],
        )

    # ------------------------------------------------------------------
    # Polls
    # ------------------------------------------------------------------

    def build_poll_task(
        self,
        credentials: dict[str, Any],
        subreddit: str,
        question: str,
        options: list[str],
        title: str | None = None,
        flair: str | None = None,
    ) -> BrowserTask:
        task = _login_prefix(credentials)
        task += f"Navigate to r/{subreddit} submit page. "
        task += "Select the 'Poll' tab. "
        task += f"Set the title to: '{question}'. "
        for i, opt in enumerate(options[:6], 1):
            task += f"Set option {i} to: '{opt}'. "
        if flair:
            task += f"Select the flair '{flair}' from the flair dropdown. "
        task += (
            "Set poll duration to 3 days. "
            "Click 'Post' to publish. "
            'Return as JSON: {"url": "...", "post_id": "..."}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url=f"https://www.reddit.com/r/{subreddit}/submit",
            ),
            context_keys=["post_creation", "poll_creation"],
        )

    # ------------------------------------------------------------------
    # Crosspost
    # ------------------------------------------------------------------

    def build_crosspost_task(
        self,
        credentials: dict[str, Any],
        target_subreddit: str,
        original_url: str,
        title: str | None = None,
        flair: str | None = None,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to the original post at: {original_url}. "
            "Click '...' or 'Share', then select 'Crosspost'. "
            f"Choose target subreddit r/{target_subreddit}. "
        )
        if title:
            task += f"Set the title to: '{title}'. "
        if flair:
            task += f"Select the flair '{flair}' from the flair dropdown. "
        task += (
            "Click 'Post'. "
            'Return as JSON: {"url": "...", "post_id": "..."}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url=original_url),
            context_keys=["crosspost"],
        )

    # ------------------------------------------------------------------
    # Analytics / karma
    # ------------------------------------------------------------------

    def build_karma_task(
        self,
        credentials: dict[str, Any],
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + "Go to your profile page. "
            "Read the karma breakdown: post karma, comment karma, total karma, account age. "
            'Return as JSON: {"post_karma": N, "comment_karma": N, '
            '"total_karma": N, "account_age_days": N}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url="https://www.reddit.com/user/me/",
            ),
            context_keys=["profile_karma"],
        )

    def build_profile_analytics_task(
        self,
        credentials: dict[str, Any],
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + "Go to your profile page. "
            "Read the karma breakdown: post karma, comment karma, total karma, account age. "
            'Return as JSON: {"post_karma": N, "comment_karma": N, '
            '"total_karma": N, "account_age_days": N}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url="https://www.reddit.com/user/me/",
            ),
            context_keys=["profile_karma"],
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
    ) -> BrowserTask:
        task = (
            "Go to https://www.reddit.com/register. "
            f"Enter the email '{email_address}' and continue. "
            f"Set the username to '{username}'. "
            f"Set the password to '{password}'. "
            "Click 'Sign Up'. "
            "If an email verification code is requested, call the "
            f"read_verification_email action with email_account_name='{email_account_name}' "
            "to get the code, then enter it and click 'Verify'. "
            "If a CAPTCHA appears, solve it visually. "
            "If a phone number is required and cannot be skipped (try 'Skip' or 'Not now' first), "
            'return {"error": "phone_verification_required"}. '
            'On success, return {"success": true}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url="https://www.reddit.com/register"),
            context_keys=["signup", "captcha_handling"],
        )
