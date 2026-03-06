"""LinkedIn platform adapter."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from src.marketing.base import BrowserTask, PlatformAdapter

if TYPE_CHECKING:
    from src.marketing.platform_knowledge import PlatformKnowledge


def _login_prefix(credentials: dict[str, Any]) -> str:
    check_already_logged_in = (
        "First check if you are already logged in by looking at the page. "
        "If the LinkedIn feed or navigation bar with your profile is visible, "
        "skip the login and proceed directly. "
        "Only log in if you see a login/sign-in page. "
    )
    if credentials.get("login_method") == "google":
        return (
            check_already_logged_in
            + "If you need to log in: click 'Sign in' then click the "
            "'Sign in with Google' button. "
            "If a Google account chooser appears, select the account "
            f"'{credentials['google_email']}'. "
            "If a Google login form appears, enter email "
            f"'{credentials['google_email']}' and click Next, "
            f"then enter password '{credentials['google_password']}' and click Next. "
            "Wait until the LinkedIn feed loads. "
            "IMPORTANT: If a CAPTCHA or 'I am not a robot' challenge appears, "
            "try to solve it. If you cannot solve it after 2 attempts, "
            "try the direct email/password login on the LinkedIn login page instead "
            f"(email: '{credentials['google_email']}', password: '{credentials['google_password']}'). "
        )
    return (
        check_already_logged_in
        + "If you need to log in: "
        f"log in with email '{credentials['username']}' "
        f"and password '{credentials['password']}'. "
    )


class LinkedInAdapter(PlatformAdapter):
    """Generates browser task descriptions for LinkedIn."""

    def __init__(self, knowledge: PlatformKnowledge | None = None) -> None:
        self._knowledge = knowledge

    @property
    def platform_name(self) -> str:
        return "linkedin"

    def _enhance(self, task: BrowserTask, context_keys: list[str] | None = None) -> BrowserTask:
        if self._knowledge:
            return self._knowledge.enhance_task("linkedin", task, context_keys)
        return task

    # ------------------------------------------------------------------
    # Core (existing)
    # ------------------------------------------------------------------

    def build_post_task(
        self,
        credentials: dict[str, Any],
        content: str,
        title: str | None = None,
        image_path: str | None = None,
        **kwargs: Any,
    ) -> BrowserTask:
        task = _login_prefix(credentials)
        task += "Click 'Start a post' on the home feed. "
        text = f"{title}\n\n{content}" if title else content
        task += f"Type this text: '{text}'. "
        if image_path:
            task += f"Upload the image from '{image_path}'. "
        if kwargs.get("url"):
            task += f"Make sure the link {kwargs['url']} is included in the text. "
        task += (
            "Click 'Post' to publish. After posting, get the post URL. "
            'Return as JSON: {"url": "...", "post_id": "..."}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url="https://www.linkedin.com"),
            context_keys=["post_creation", "modal_behavior"],
        )

    def build_metrics_task(
        self,
        credentials: dict[str, Any],
        platform_post_id: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to the post at: {platform_post_id}. "
            "Read the current reactions, comments, and reposts count. "
            'Return as JSON: {"likes": N, "comments": N, "shares": N, '
            '"views": 0, "extra": {"reactions_breakdown": {}}}.'
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
            f"Go to the LinkedIn post at: {platform_post_id}. "
            f"Read the top {limit} comments. For each comment, extract the "
            "author name, text, and any available comment identifier. "
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
            "Click the '...' menu on the post, then click 'Delete post'. "
            "Confirm deletion. "
            'Return as JSON: {"deleted": true}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url=platform_post_id),
            context_keys=["modal_behavior"],
        )

    # ------------------------------------------------------------------
    # Feed interactions
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
                f"Go to the LinkedIn search page and search for '{query}'. "
                "Filter by 'Posts'. "
            )
        else:
            task += "Go to the LinkedIn home feed. "
        task += (
            f"Scroll through and collect up to {limit} posts. "
            "For each post, extract: author name, headline, content text, "
            "post URL, likes count, comments count. "
            'Return as JSON: {"posts": [{"author": "...", "headline": "...", '
            '"content": "...", "url": "...", "likes": N, "comments": N}]}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url="https://www.linkedin.com/feed/"),
            context_keys=["feed_navigation", "scroll_behavior"],
        )

    def build_like_task(
        self,
        credentials: dict[str, Any],
        post_url: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to the post at: {post_url}. "
            "Click the 'Like' button on the post. "
            'Return as JSON: {"liked": true, "post_url": "..."}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url=post_url),
            context_keys=["reactions"],
        )

    def build_comment_external_task(
        self,
        credentials: dict[str, Any],
        post_url: str,
        text: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to the post at: {post_url}. "
            "Click the 'Comment' button to open the comment box. "
            f"Type this comment: '{text}'. "
            "Press Enter or click the submit button to post the comment. "
            'Return as JSON: {"commented": true, "post_url": "..."}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url=post_url),
            context_keys=["comments_section"],
        )

    def build_repost_task(
        self,
        credentials: dict[str, Any],
        post_url: str,
        commentary: str | None = None,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to the post at: {post_url}. "
            "Click the 'Repost' button. "
        )
        if commentary:
            task += (
                "Select 'Repost with your thoughts'. "
                f"Type this commentary: '{commentary}'. "
                "Click 'Post'. "
            )
        else:
            task += "Select 'Repost' (instant repost without commentary). "
        task += 'Return as JSON: {"reposted": true, "post_url": "..."}.'
        return self._enhance(
            BrowserTask(task_description=task, start_url=post_url),
            context_keys=["repost_flow"],
        )

    # ------------------------------------------------------------------
    # Networking
    # ------------------------------------------------------------------

    def build_connection_request_task(
        self,
        credentials: dict[str, Any],
        profile_url: str,
        note: str | None = None,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to the profile at: {profile_url}. "
            "Click the 'Connect' button. "
        )
        if note:
            task += (
                "If prompted, click 'Add a note'. "
                f"Type this note: '{note}'. "
            )
        task += (
            "Click 'Send'. "
            'Return as JSON: {"sent": true, "profile_url": "..."}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url=profile_url),
            context_keys=["connection_request", "modal_behavior"],
        )

    def build_accept_connections_task(
        self,
        credentials: dict[str, Any],
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + "Go to https://www.linkedin.com/mynetwork/invitation-manager/. "
            "Accept all pending connection requests by clicking 'Accept' on each. "
            "Count how many were accepted. "
            'Return as JSON: {"accepted": N, "profiles": ["name1", "name2"]}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url="https://www.linkedin.com/mynetwork/invitation-manager/",
            ),
            context_keys=["invitation_manager"],
        )

    def build_send_message_task(
        self,
        credentials: dict[str, Any],
        recipient_url: str,
        message: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + f"Navigate to the profile at: {recipient_url}. "
            "Click the 'Message' button. "
            f"Type this message: '{message}'. "
            "Press Enter or click Send to deliver the message. "
            'Return as JSON: {"sent": true, "recipient_url": "..."}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url=recipient_url),
            context_keys=["messaging"],
        )

    def build_search_people_task(
        self,
        credentials: dict[str, Any],
        filters: dict[str, Any] | None = None,
    ) -> BrowserTask:
        task = _login_prefix(credentials)
        filters = filters or {}
        search_url = "https://www.linkedin.com/search/results/people/"

        params = []
        if filters.get("keywords"):
            params.append(f"keywords={filters['keywords']}")
        if filters.get("role"):
            params.append(f"title={filters['role']}")
        if filters.get("company"):
            params.append(f"company={filters['company']}")

        if params:
            search_url += "?" + "&".join(params)

        task += (
            f"Go to: {search_url}. "
            "Collect up to 10 profiles from the results. "
            "For each profile, extract: name, headline, profile URL, location. "
            'Return as JSON: {"profiles": [{"name": "...", "headline": "...", '
            '"url": "...", "location": "..."}]}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url=search_url),
            context_keys=["people_search"],
        )

    # ------------------------------------------------------------------
    # Advanced content types
    # ------------------------------------------------------------------

    def build_article_task(
        self,
        credentials: dict[str, Any],
        title: str,
        content: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + "Go to https://www.linkedin.com/pulse/ to create a new article. "
            "Click 'Write article' or 'New article'. "
            f"Set the title to: '{title}'. "
            f"Write this content in the article body: '{content}'. "
            "Click 'Publish'. "
            'Return as JSON: {"url": "...", "title": "..."}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url="https://www.linkedin.com/pulse/"),
            context_keys=["article_editor"],
        )

    def build_carousel_task(
        self,
        credentials: dict[str, Any],
        content: str,
        document_path: str,
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + "Click 'Start a post' on the home feed. "
            "Click the document icon in the post toolbar. "
            f"Upload the document from: '{document_path}'. "
            f"Add this text to the post: '{content}'. "
            "Click 'Post' to publish. "
            'Return as JSON: {"url": "...", "post_id": "..."}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url="https://www.linkedin.com/feed/"),
            context_keys=["post_creation", "document_upload"],
        )

    def build_poll_task(
        self,
        credentials: dict[str, Any],
        question: str,
        options: list[str],
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + "Click 'Start a post' on the home feed. "
            "Click the '+' or 'More' icon, then select 'Create a poll'. "
            f"Enter this question: '{question}'. "
        )
        for i, opt in enumerate(options[:4], 1):
            task += f"Set option {i} to: '{opt}'. "
        task += (
            "Set duration to 1 week. "
            "Click 'Post' to publish. "
            'Return as JSON: {"url": "...", "post_id": "..."}.'
        )
        return self._enhance(
            BrowserTask(task_description=task, start_url="https://www.linkedin.com/feed/"),
            context_keys=["post_creation", "poll_creation"],
        )

    # ------------------------------------------------------------------
    # Account creation
    # ------------------------------------------------------------------

    def build_signup_task(
        self,
        first_name: str,
        last_name: str,
        email_address: str,
        password: str,
        email_account_name: str,
        login_method: str = "email",
        google_email: str | None = None,
        google_password: str | None = None,
    ) -> BrowserTask:
        if login_method == "google":
            task = (
                "Go to https://www.linkedin.com/signup. "
                "Click the 'Sign up with Google' or 'Continue with Google' button. "
                f"If a Google account chooser appears, select '{google_email}'. "
                "If a Google login form appears, enter email "
                f"'{google_email}' and click Next, "
                f"then enter password '{google_password}' and click Next. "
                "If Google asks to confirm access for LinkedIn, click 'Allow' or 'Continue'. "
                "If LinkedIn asks for first name / last name after Google auth, "
                f"fill in '{first_name}' and '{last_name}'. "
                "If a CAPTCHA appears, solve it visually. "
                "If a phone number is required and cannot be skipped "
                "(try 'Skip' or 'Not now' first), "
                'return {"error": "phone_verification_required"}. '
                'On success, return {"success": true}.'
            )
        else:
            task = (
                "Go to https://www.linkedin.com/signup. "
                f"Fill in the first name field with '{first_name}'. "
                f"Fill in the last name field with '{last_name}'. "
                f"Fill in the email field with '{email_address}'. "
                f"Fill in the password field with '{password}'. "
                "Click the 'Agree & Join' button. "
                "If a verification code is requested, call the "
                f"read_verification_email action with email_account_name='{email_account_name}' "
                "to get the code, then enter it in the verification field and click 'Verify'. "
                "If a CAPTCHA appears, solve it visually. "
                "If a phone number is required and cannot be skipped "
                "(try 'Skip' or 'Not now' first), "
                'return {"error": "phone_verification_required"}. '
                'On success, return {"success": true}.'
            )
        return self._enhance(
            BrowserTask(task_description=task, start_url="https://www.linkedin.com/signup"),
            context_keys=["signup", "captcha_handling"],
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
            + "Go to https://www.linkedin.com/dashboard/. "
            "Read the profile analytics: profile views, post impressions, "
            "search appearances, follower count, connection count. "
            'Return as JSON: {"profile_views": N, "post_impressions": N, '
            '"search_appearances": N, "follower_count": N, "connection_count": N}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url="https://www.linkedin.com/dashboard/",
            ),
            context_keys=["analytics_dashboard"],
        )

    def build_ssi_score_task(
        self,
        credentials: dict[str, Any],
    ) -> BrowserTask:
        task = (
            _login_prefix(credentials)
            + "Go to https://www.linkedin.com/sales/ssi. "
            "Read the SSI score and its four components. "
            'Return as JSON: {"ssi_score": N, "components": {'
            '"professional_brand": N, "right_people": N, '
            '"engage_insights": N, "build_relationships": N}}.'
        )
        return self._enhance(
            BrowserTask(
                task_description=task,
                start_url="https://www.linkedin.com/sales/ssi",
            ),
            context_keys=["ssi_page"],
        )
