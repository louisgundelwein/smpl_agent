"""Dedicated Reddit tool: feed, subreddits, content, analytics."""

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from src.marketing.base import BrowserTask
from src.marketing.reddit import RedditAdapter
from src.marketing.platform_knowledge import PlatformKnowledge
from src.marketing_store import MarketingStore
from src.tools.base import Tool

logger = logging.getLogger(__name__)


class RedditTool(Tool):
    """Full Reddit integration: feed browsing, subreddits, content, analytics.

    All platform interactions go through browser-use via the RedditAdapter.
    Platform knowledge (static guide + dynamic learnings) is injected into
    every browser task for improved reliability.
    """

    def __init__(
        self,
        store: MarketingStore,
        knowledge: PlatformKnowledge,
        adapter: RedditAdapter,
        openai_api_key: str,
        openai_model: str,
        openai_base_url: str | None = None,
        timeout: int = 300,
        action_delay: int = 3,
        browser_profiles_dir: str = "browser_profiles",
        email_store: "Any | None" = None,
    ) -> None:
        self._store = store
        self._knowledge = knowledge
        self._adapter = adapter
        self._openai_api_key = openai_api_key
        self._openai_model = openai_model
        self._openai_base_url = openai_base_url
        self._timeout = timeout
        self._action_delay = action_delay
        self._last_action_time = 0.0
        self._browser_profiles_dir = browser_profiles_dir
        self._email_store = email_store

    @property
    def name(self) -> str:
        return "reddit"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "reddit",
                "description": (
                    "Reddit platform tool. Browse feed and subreddits, vote on posts, "
                    "comment, create posts (text/link/image/poll/crosspost), "
                    "manage subreddit memberships, track karma and analytics, "
                    "and manage drafts. All actions use browser automation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "create_account",
                                "browse_feed", "browse_subreddit", "search_posts",
                                "upvote", "downvote", "comment", "reply_to_comment",
                                "create_post", "delete_post",
                                "send_message", "read_inbox",
                                "join_subreddit", "leave_subreddit", "list_subreddits",
                                "get_post_performance", "get_karma", "get_analytics_report",
                                "save_draft", "list_drafts", "publish_draft",
                                "explore_platform", "record_learning",
                            ],
                        },
                        "account": {
                            "type": "string",
                            "description": "Registered Reddit account name.",
                        },
                        "subreddit": {
                            "type": "string",
                            "description": "Subreddit name (without r/ prefix).",
                        },
                        "post_url": {
                            "type": "string",
                            "description": "URL of a Reddit post.",
                        },
                        "comment_id": {
                            "type": "string",
                            "description": "Comment identifier for reply_to_comment.",
                        },
                        "content": {
                            "type": "string",
                            "description": "Text content for posts, comments, messages.",
                        },
                        "title": {
                            "type": "string",
                            "description": "Title for posts or drafts.",
                        },
                        "query": {
                            "type": "string",
                            "description": "Search query.",
                        },
                        "message": {
                            "type": "string",
                            "description": "Message text for DMs.",
                        },
                        "recipient": {
                            "type": "string",
                            "description": "Username to send a message to.",
                        },
                        "post_type": {
                            "type": "string",
                            "enum": ["text", "link", "image", "poll", "crosspost"],
                            "description": "Type of post to create.",
                        },
                        "url": {
                            "type": "string",
                            "description": "Link URL for link posts.",
                        },
                        "image_path": {
                            "type": "string",
                            "description": "Path to image for image posts.",
                        },
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Poll options (2-6 choices).",
                        },
                        "flair": {
                            "type": "string",
                            "description": "Post flair text.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results (default 10).",
                        },
                        "days": {
                            "type": "integer",
                            "description": "Time window for analytics (default 30).",
                        },
                        "sort": {
                            "type": "string",
                            "enum": ["hot", "new", "top", "rising"],
                            "description": "Sort order for feed/subreddit browsing.",
                        },
                        "draft_id": {
                            "type": "integer",
                            "description": "Draft ID for publish/update.",
                        },
                        "area": {
                            "type": "string",
                            "description": "Platform area to explore (feed, messaging, subreddits).",
                        },
                        "key": {
                            "type": "string",
                            "description": "Learning key for record_learning.",
                        },
                        "value": {
                            "type": "string",
                            "description": "Learning value for record_learning.",
                        },
                        "metadata": {
                            "type": "object",
                            "description": "Extra metadata for drafts (poll options, crosspost info, etc.).",
                        },
                        "username": {
                            "type": "string",
                            "description": "Username for account creation.",
                        },
                        "password": {
                            "type": "string",
                            "description": "Password for account creation.",
                        },
                        "email_account": {
                            "type": "string",
                            "description": "Name of registered email account for verification.",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        if action == "create_account":
            try:
                return self._action_create_account(kwargs)
            except Exception as exc:
                return json.dumps({"error": str(exc)})
        try:
            handler = getattr(self, f"_action_{action}", None)
            if handler is None:
                return json.dumps({"error": f"Unknown action: {action}"})
            return handler(kwargs)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    # ------------------------------------------------------------------
    # Account resolution
    # ------------------------------------------------------------------

    def _get_credentials(self, kw: dict) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return (account_dict, credentials_dict) or raise."""
        account_name = kw.get("account")
        if not account_name:
            raise ValueError("account is required")
        acct = self._store.get_account(account_name)
        if not acct:
            raise ValueError(f"Account '{account_name}' not found")
        if acct["platform"] != "reddit":
            raise ValueError(f"Account '{account_name}' is not a Reddit account")
        creds = acct["credentials"]
        if isinstance(creds, str):
            creds = json.loads(creds)
        return acct, creds

    # ------------------------------------------------------------------
    # Browser execution
    # ------------------------------------------------------------------

    def _enforce_delay(self) -> None:
        elapsed = time.time() - self._last_action_time
        if elapsed < self._action_delay:
            time.sleep(self._action_delay - elapsed)
        self._last_action_time = time.time()

    async def _run_browser_task(
        self, task: BrowserTask, account_name: str | None = None,
    ) -> str:
        from browser_use import Agent as BrowserAgent, Browser, BrowserConfig, Controller
        from langchain_openai import ChatOpenAI

        if account_name:
            profile_dir = Path(self._browser_profiles_dir) / account_name
            profile_dir.mkdir(parents=True, exist_ok=True)
            browser_config = BrowserConfig(
                headless=True, user_data_dir=str(profile_dir),
            )
        else:
            browser_config = BrowserConfig(headless=True)
        browser = Browser(config=browser_config)

        llm_kwargs: dict[str, Any] = {
            "model": self._openai_model,
            "api_key": self._openai_api_key,
        }
        if self._openai_base_url:
            llm_kwargs["base_url"] = self._openai_base_url
        llm = ChatOpenAI(**llm_kwargs)

        full_task = task.task_description
        if task.start_url:
            full_task = f"Go to {task.start_url}. Then: {full_task}"

        controller = Controller()
        if self._email_store:
            from src.marketing.email_helper import EmailVerificationReader

            email_store = self._email_store

            @controller.action("Read verification email code from inbox")
            async def read_verification_email(email_account_name: str) -> str:
                reader = EmailVerificationReader(email_store)
                return json.dumps(reader.read_verification_code(email_account_name))

        agent = BrowserAgent(
            task=full_task, llm=llm, browser=browser, controller=controller,
        )

        try:
            result = await asyncio.wait_for(
                agent.run(), timeout=self._timeout,
            )
        finally:
            await browser.close()

        return str(result)

    def _exec_browser(self, task: BrowserTask, account_name: str | None = None) -> str:
        self._enforce_delay()
        return asyncio.run(self._run_browser_task(task, account_name))

    # ------------------------------------------------------------------
    # Feed browsing
    # ------------------------------------------------------------------

    def _action_browse_feed(self, kw: dict) -> str:
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_feed_browse_task(
            creds, query=kw.get("query"), limit=kw.get("limit", 10),
            sort=kw.get("sort", "hot"),
        )
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_browse_subreddit(self, kw: dict) -> str:
        subreddit = kw.get("subreddit")
        if not subreddit:
            return json.dumps({"error": "subreddit is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_subreddit_browse_task(
            creds, subreddit, limit=kw.get("limit", 10),
            sort=kw.get("sort", "hot"),
        )
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_search_posts(self, kw: dict) -> str:
        query = kw.get("query")
        if not query:
            return json.dumps({"error": "query is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_search_task(
            creds, query, subreddit=kw.get("subreddit"),
            sort=kw.get("sort", "hot"), limit=kw.get("limit", 10),
        )
        return self._exec_browser(task, account_name=kw.get("account"))

    # ------------------------------------------------------------------
    # Interactions
    # ------------------------------------------------------------------

    def _action_upvote(self, kw: dict) -> str:
        post_url = kw.get("post_url")
        if not post_url:
            return json.dumps({"error": "post_url is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_vote_task(creds, post_url, direction="up")
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_downvote(self, kw: dict) -> str:
        post_url = kw.get("post_url")
        if not post_url:
            return json.dumps({"error": "post_url is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_vote_task(creds, post_url, direction="down")
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_comment(self, kw: dict) -> str:
        post_url = kw.get("post_url")
        content = kw.get("content")
        if not post_url or not content:
            return json.dumps({"error": "post_url and content are required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_comment_task(creds, post_url, content)
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_reply_to_comment(self, kw: dict) -> str:
        post_url = kw.get("post_url")
        comment_id = kw.get("comment_id")
        content = kw.get("content")
        if not post_url or not comment_id or not content:
            return json.dumps({"error": "post_url, comment_id, and content are required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_reply_task(creds, post_url, comment_id, content)
        return self._exec_browser(task, account_name=kw.get("account"))

    # ------------------------------------------------------------------
    # Content creation
    # ------------------------------------------------------------------

    def _action_create_post(self, kw: dict) -> str:
        subreddit = kw.get("subreddit")
        if not subreddit:
            return json.dumps({"error": "subreddit is required"})
        post_type = kw.get("post_type", "text")
        _, creds = self._get_credentials(kw)

        if post_type == "poll":
            content = kw.get("content")
            options = kw.get("options")
            if not content or not options:
                return json.dumps({"error": "content (question) and options are required for polls"})
            if len(options) < 2:
                return json.dumps({"error": "At least 2 options are required"})
            task = self._adapter.build_poll_task(
                creds, subreddit, content, options,
                title=kw.get("title"), flair=kw.get("flair"),
            )
        elif post_type == "crosspost":
            post_url = kw.get("post_url")
            if not post_url:
                return json.dumps({"error": "post_url is required for crosspost"})
            task = self._adapter.build_crosspost_task(
                creds, subreddit, post_url,
                title=kw.get("title"), flair=kw.get("flair"),
            )
        elif post_type == "image":
            image_path = kw.get("image_path")
            if not image_path:
                return json.dumps({"error": "image_path is required for image posts"})
            task = self._adapter.build_post_task(
                creds, kw.get("content", ""), subreddit=subreddit,
                title=kw.get("title"), image_path=image_path,
                flair=kw.get("flair"),
            )
        elif post_type == "link":
            url = kw.get("url")
            if not url:
                return json.dumps({"error": "url is required for link posts"})
            task = self._adapter.build_post_task(
                creds, kw.get("content", ""), subreddit=subreddit,
                title=kw.get("title"), url=url,
                flair=kw.get("flair"),
            )
        else:
            content = kw.get("content")
            if not content:
                return json.dumps({"error": "content is required"})
            task = self._adapter.build_post_task(
                creds, content, subreddit=subreddit,
                title=kw.get("title"), flair=kw.get("flair"),
            )

        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_delete_post(self, kw: dict) -> str:
        post_url = kw.get("post_url")
        if not post_url:
            return json.dumps({"error": "post_url is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_delete_task(creds, post_url)
        return self._exec_browser(task, account_name=kw.get("account"))

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    def _action_send_message(self, kw: dict) -> str:
        recipient = kw.get("recipient")
        message = kw.get("message")
        if not recipient or not message:
            return json.dumps({"error": "recipient and message are required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_send_message_task(creds, recipient, message)
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_read_inbox(self, kw: dict) -> str:
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_read_inbox_task(creds, limit=kw.get("limit", 10))
        return self._exec_browser(task, account_name=kw.get("account"))

    # ------------------------------------------------------------------
    # Subreddit management
    # ------------------------------------------------------------------

    def _action_join_subreddit(self, kw: dict) -> str:
        subreddit = kw.get("subreddit")
        if not subreddit:
            return json.dumps({"error": "subreddit is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_join_subreddit_task(creds, subreddit)
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_leave_subreddit(self, kw: dict) -> str:
        subreddit = kw.get("subreddit")
        if not subreddit:
            return json.dumps({"error": "subreddit is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_leave_subreddit_task(creds, subreddit)
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_list_subreddits(self, kw: dict) -> str:
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_list_subreddits_task(creds)
        return self._exec_browser(task, account_name=kw.get("account"))

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def _action_get_post_performance(self, kw: dict) -> str:
        post_url = kw.get("post_url")
        if not post_url:
            return json.dumps({"error": "post_url is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_metrics_task(creds, post_url)
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_get_karma(self, kw: dict) -> str:
        acct, creds = self._get_credentials(kw)
        task = self._adapter.build_karma_task(creds)
        result_str = self._exec_browser(task, account_name=kw.get("account"))

        try:
            data = json.loads(result_str)
            self._store.record_reddit_profile_metrics(
                account_id=acct["id"],
                post_karma=data.get("post_karma"),
                comment_karma=data.get("comment_karma"),
                total_karma=data.get("total_karma"),
                account_age_days=data.get("account_age_days"),
            )
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Could not store Reddit profile metrics: %s", exc)

        return result_str

    def _action_get_analytics_report(self, kw: dict) -> str:
        acct, _ = self._get_credentials(kw)
        days = kw.get("days", 30)
        history = self._store.get_reddit_profile_metrics_history(acct["id"], days=days)
        if not history:
            return json.dumps({
                "report": "No Reddit profile metrics recorded yet. "
                "Use get_karma first to collect data.",
                "days": days,
            })
        latest = history[-1]
        report = {
            "days": days,
            "data_points": len(history),
            "latest": {
                "post_karma": latest.get("post_karma"),
                "comment_karma": latest.get("comment_karma"),
                "total_karma": latest.get("total_karma"),
                "account_age_days": latest.get("account_age_days"),
                "recorded_at": str(latest.get("recorded_at")),
            },
        }
        if len(history) >= 2:
            first = history[0]
            report["growth"] = {
                "post_karma_change": (latest.get("post_karma") or 0) - (first.get("post_karma") or 0),
                "comment_karma_change": (latest.get("comment_karma") or 0) - (first.get("comment_karma") or 0),
                "total_karma_change": (latest.get("total_karma") or 0) - (first.get("total_karma") or 0),
            }
        return json.dumps({"report": report}, default=str)

    # ------------------------------------------------------------------
    # Drafts
    # ------------------------------------------------------------------

    def _action_save_draft(self, kw: dict) -> str:
        content = kw.get("content")
        if not content:
            return json.dumps({"error": "content is required"})
        acct, _ = self._get_credentials(kw)
        draft_id = self._store.create_draft(
            account_id=acct["id"],
            content=content,
            post_type=kw.get("post_type", "text"),
            title=kw.get("title"),
            metadata=kw.get("metadata"),
        )
        return json.dumps({"saved": True, "draft_id": draft_id})

    def _action_list_drafts(self, kw: dict) -> str:
        acct, _ = self._get_credentials(kw)
        drafts = self._store.list_drafts(account_id=acct["id"])
        return json.dumps({"drafts": drafts, "count": len(drafts)}, default=str)

    def _action_publish_draft(self, kw: dict) -> str:
        draft_id = kw.get("draft_id")
        if not draft_id:
            return json.dumps({"error": "draft_id is required"})
        draft = self._store.get_draft(draft_id)
        if not draft:
            return json.dumps({"error": f"Draft {draft_id} not found"})

        subreddit = kw.get("subreddit")
        if not subreddit:
            return json.dumps({"error": "subreddit is required to publish a draft"})

        _, creds = self._get_credentials(kw)
        post_type = draft["post_type"]
        metadata = draft.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        if post_type == "poll":
            options = metadata.get("options", [])
            task = self._adapter.build_poll_task(
                creds, subreddit, draft["content"], options,
                title=draft.get("title"),
            )
        elif post_type == "crosspost":
            post_url = metadata.get("post_url", "")
            task = self._adapter.build_crosspost_task(
                creds, subreddit, post_url,
                title=draft.get("title"),
            )
        elif post_type == "link":
            task = self._adapter.build_post_task(
                creds, draft["content"], subreddit=subreddit,
                title=draft.get("title"), url=metadata.get("url"),
            )
        elif post_type == "image":
            task = self._adapter.build_post_task(
                creds, draft["content"], subreddit=subreddit,
                title=draft.get("title"), image_path=metadata.get("image_path"),
            )
        else:
            task = self._adapter.build_post_task(
                creds, draft["content"], subreddit=subreddit,
                title=draft.get("title"),
            )

        result = self._exec_browser(task, account_name=kw.get("account"))
        self._store.delete_draft(draft_id)
        return result

    # ------------------------------------------------------------------
    # Knowledge
    # ------------------------------------------------------------------

    def _action_explore_platform(self, kw: dict) -> str:
        area = kw.get("area", "feed")
        _, creds = self._get_credentials(kw)

        task_desc = (
            f"Explore the Reddit '{area}' area. "
            "Navigate around, note UI elements, buttons, and behavior. "
            "Return observations as JSON: "
            '{"observations": [{"key": "...", "value": "...", "confidence": 0.8}]}.'
        )
        task = BrowserTask(
            task_description=(
                f"Log in with username '{creds['username']}' and password '{creds['password']}'. "
                + task_desc
            ),
            start_url="https://www.reddit.com",
        )
        result_str = self._exec_browser(task, account_name=kw.get("account"))

        try:
            data = json.loads(result_str)
            for obs in data.get("observations", []):
                self._knowledge.record_learning(
                    platform="reddit",
                    key=obs["key"],
                    value=obs["value"],
                    confidence=obs.get("confidence", 0.5),
                )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Could not parse exploration results: %s", exc)

        return result_str

    def _action_record_learning(self, kw: dict) -> str:
        key = kw.get("key")
        value = kw.get("value")
        if not key or not value:
            return json.dumps({"error": "key and value are required"})
        self._knowledge.record_learning(
            platform="reddit", key=key, value=value, confidence=0.8,
        )
        return json.dumps({"recorded": True, "key": key})

    # ------------------------------------------------------------------
    # Account creation
    # ------------------------------------------------------------------

    def _action_create_account(self, kw: dict) -> str:
        username = kw.get("username")
        password = kw.get("password")
        email_account = kw.get("email_account")

        if not all([username, password, email_account]):
            return json.dumps({
                "error": "username, password, and email_account are required",
            })

        if not self._email_store:
            return json.dumps({"error": "No email store configured — cannot create account"})

        email_acct = self._email_store.get(email_account)
        if not email_acct:
            return json.dumps({"error": f"Email account '{email_account}' not found"})

        email_address = email_acct["email_address"]

        task = self._adapter.build_signup_task(
            username=username,
            password=password,
            email_address=email_address,
            email_account_name=email_account,
        )

        result_str = self._exec_browser(task)

        try:
            data = json.loads(result_str)
        except (json.JSONDecodeError, TypeError):
            return json.dumps({"error": f"Unexpected browser result: {result_str}"})

        if data.get("error"):
            return json.dumps({"error": data["error"]})

        if data.get("success"):
            safe_name = re.sub(r"[^a-z0-9-]", "", f"rd-{username}".lower())
            account_id = self._store.add_account(
                name=safe_name,
                platform="reddit",
                credentials={"username": username, "password": password},
                config={"email_account": email_account},
            )
            profile_dir = Path(self._browser_profiles_dir) / safe_name
            profile_dir.mkdir(parents=True, exist_ok=True)
            return json.dumps({
                "created": True,
                "account_name": safe_name,
                "account_id": account_id,
            })

        return json.dumps({"error": "Account creation did not succeed", "details": data})
