"""Dedicated LinkedIn tool: feed, networking, content, analytics."""

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from src.marketing.base import BrowserTask
from src.marketing.linkedin import LinkedInAdapter
from src.marketing.platform_knowledge import PlatformKnowledge
from src.marketing_store import MarketingStore
from src.tools.base import Tool

logger = logging.getLogger(__name__)


class LinkedInTool(Tool):
    """Full LinkedIn integration: feed browsing, networking, content, analytics.

    All platform interactions go through browser-use via the LinkedInAdapter.
    Platform knowledge (static guide + dynamic learnings) is injected into
    every browser task for improved reliability.
    """

    def __init__(
        self,
        store: MarketingStore,
        knowledge: PlatformKnowledge,
        adapter: LinkedInAdapter,
        openai_api_key: str,
        openai_model: str,
        openai_base_url: str | None = None,
        timeout: int = 300,
        action_delay: int = 2,
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
        return "linkedin"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "linkedin",
                "description": (
                    "LinkedIn platform tool. Browse feed, interact with posts, "
                    "manage network connections, create various content types "
                    "(posts, articles, carousels, polls), track analytics, "
                    "and manage drafts. All actions use browser automation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "create_account",
                                "browse_feed", "like_post", "comment_post", "repost",
                                "send_connection", "accept_connections",
                                "send_message", "search_people",
                                "create_post", "create_article",
                                "create_carousel", "create_poll",
                                "save_draft", "list_drafts", "publish_draft",
                                "get_profile_analytics", "get_post_performance",
                                "get_ssi_score", "get_analytics_report",
                                "explore_platform", "record_learning",
                            ],
                        },
                        "account": {
                            "type": "string",
                            "description": "Registered LinkedIn account name.",
                        },
                        "post_url": {
                            "type": "string",
                            "description": "URL of a LinkedIn post.",
                        },
                        "profile_url": {
                            "type": "string",
                            "description": "URL of a LinkedIn profile.",
                        },
                        "content": {
                            "type": "string",
                            "description": "Text content for posts, comments, messages.",
                        },
                        "title": {
                            "type": "string",
                            "description": "Title for articles or drafts.",
                        },
                        "query": {
                            "type": "string",
                            "description": "Search query for feed or people.",
                        },
                        "note": {
                            "type": "string",
                            "description": "Note for connection requests.",
                        },
                        "message": {
                            "type": "string",
                            "description": "Message text for DMs.",
                        },
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Poll options (2-4 choices).",
                        },
                        "filters": {
                            "type": "object",
                            "description": "People search filters (keywords, role, company, location).",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results (default 10).",
                        },
                        "days": {
                            "type": "integer",
                            "description": "Time window for analytics (default 30).",
                        },
                        "draft_id": {
                            "type": "integer",
                            "description": "Draft ID for publish/update.",
                        },
                        "post_type": {
                            "type": "string",
                            "enum": ["text", "article", "carousel", "poll"],
                            "description": "Type of draft.",
                        },
                        "document_path": {
                            "type": "string",
                            "description": "Path to PDF for carousel posts.",
                        },
                        "image_path": {
                            "type": "string",
                            "description": "Path to image for posts.",
                        },
                        "url": {
                            "type": "string",
                            "description": "Link to include in post.",
                        },
                        "area": {
                            "type": "string",
                            "description": "Platform area to explore (feed, messaging, analytics).",
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
                            "description": "Extra metadata for drafts (slides, poll_options, etc.).",
                        },
                        "first_name": {
                            "type": "string",
                            "description": "First name for account creation.",
                        },
                        "last_name": {
                            "type": "string",
                            "description": "Last name for account creation.",
                        },
                        "email_account": {
                            "type": "string",
                            "description": "Name of registered email account for verification.",
                        },
                        "linkedin_password": {
                            "type": "string",
                            "description": "Password for the new LinkedIn account.",
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
        if acct["platform"] != "linkedin":
            raise ValueError(f"Account '{account_name}' is not a LinkedIn account")
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
    # Feed interactions
    # ------------------------------------------------------------------

    def _action_browse_feed(self, kw: dict) -> str:
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_feed_browse_task(
            creds, query=kw.get("query"), limit=kw.get("limit", 10),
        )
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_like_post(self, kw: dict) -> str:
        post_url = kw.get("post_url")
        if not post_url:
            return json.dumps({"error": "post_url is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_like_task(creds, post_url)
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_comment_post(self, kw: dict) -> str:
        post_url = kw.get("post_url")
        content = kw.get("content")
        if not post_url or not content:
            return json.dumps({"error": "post_url and content are required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_comment_external_task(creds, post_url, content)
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_repost(self, kw: dict) -> str:
        post_url = kw.get("post_url")
        if not post_url:
            return json.dumps({"error": "post_url is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_repost_task(
            creds, post_url, commentary=kw.get("content"),
        )
        return self._exec_browser(task, account_name=kw.get("account"))

    # ------------------------------------------------------------------
    # Networking
    # ------------------------------------------------------------------

    def _action_send_connection(self, kw: dict) -> str:
        profile_url = kw.get("profile_url")
        if not profile_url:
            return json.dumps({"error": "profile_url is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_connection_request_task(
            creds, profile_url, note=kw.get("note"),
        )
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_accept_connections(self, kw: dict) -> str:
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_accept_connections_task(creds)
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_send_message(self, kw: dict) -> str:
        profile_url = kw.get("profile_url")
        message = kw.get("message")
        if not profile_url or not message:
            return json.dumps({"error": "profile_url and message are required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_send_message_task(creds, profile_url, message)
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_search_people(self, kw: dict) -> str:
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_search_people_task(
            creds, filters=kw.get("filters"),
        )
        return self._exec_browser(task, account_name=kw.get("account"))

    # ------------------------------------------------------------------
    # Content creation
    # ------------------------------------------------------------------

    def _action_create_post(self, kw: dict) -> str:
        content = kw.get("content")
        if not content:
            return json.dumps({"error": "content is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_post_task(
            creds, content,
            title=kw.get("title"),
            image_path=kw.get("image_path"),
            url=kw.get("url"),
        )
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_create_article(self, kw: dict) -> str:
        title = kw.get("title")
        content = kw.get("content")
        if not title or not content:
            return json.dumps({"error": "title and content are required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_article_task(creds, title, content)
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_create_carousel(self, kw: dict) -> str:
        content = kw.get("content")
        document_path = kw.get("document_path")
        if not content or not document_path:
            return json.dumps({"error": "content and document_path are required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_carousel_task(creds, content, document_path)
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_create_poll(self, kw: dict) -> str:
        content = kw.get("content")
        options = kw.get("options")
        if not content or not options:
            return json.dumps({"error": "content (question) and options are required"})
        if len(options) < 2:
            return json.dumps({"error": "At least 2 options are required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_poll_task(creds, content, options)
        return self._exec_browser(task, account_name=kw.get("account"))

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

        _, creds = self._get_credentials(kw)
        post_type = draft["post_type"]
        metadata = draft.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        if post_type == "article":
            task = self._adapter.build_article_task(
                creds, draft.get("title", ""), draft["content"],
            )
        elif post_type == "carousel":
            doc_path = metadata.get("document_path", "")
            task = self._adapter.build_carousel_task(creds, draft["content"], doc_path)
        elif post_type == "poll":
            options = metadata.get("options", [])
            task = self._adapter.build_poll_task(creds, draft["content"], options)
        else:
            task = self._adapter.build_post_task(
                creds, draft["content"], title=draft.get("title"),
            )

        result = self._exec_browser(task, account_name=kw.get("account"))
        self._store.delete_draft(draft_id)
        return result

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def _action_get_profile_analytics(self, kw: dict) -> str:
        acct, creds = self._get_credentials(kw)
        task = self._adapter.build_profile_analytics_task(creds)
        result_str = self._exec_browser(task, account_name=kw.get("account"))

        # Try to store the metrics
        try:
            data = json.loads(result_str)
            self._store.record_profile_metrics(
                account_id=acct["id"],
                profile_views=data.get("profile_views"),
                ssi_score=data.get("ssi_score"),
                follower_count=data.get("follower_count"),
                connection_count=data.get("connection_count"),
            )
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Could not store profile metrics: %s", exc)

        return result_str

    def _action_get_post_performance(self, kw: dict) -> str:
        post_url = kw.get("post_url")
        if not post_url:
            return json.dumps({"error": "post_url is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_metrics_task(creds, post_url)
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_get_ssi_score(self, kw: dict) -> str:
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_ssi_score_task(creds)
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_get_analytics_report(self, kw: dict) -> str:
        acct, _ = self._get_credentials(kw)
        days = kw.get("days", 30)
        history = self._store.get_profile_metrics_history(acct["id"], days=days)
        if not history:
            return json.dumps({
                "report": "No profile metrics recorded yet. "
                "Use get_profile_analytics first to collect data.",
                "days": days,
            })
        latest = history[-1]
        report = {
            "days": days,
            "data_points": len(history),
            "latest": {
                "profile_views": latest.get("profile_views"),
                "ssi_score": latest.get("ssi_score"),
                "follower_count": latest.get("follower_count"),
                "connection_count": latest.get("connection_count"),
                "recorded_at": str(latest.get("recorded_at")),
            },
        }
        if len(history) >= 2:
            first = history[0]
            report["growth"] = {
                "follower_change": (latest.get("follower_count") or 0) - (first.get("follower_count") or 0),
                "connection_change": (latest.get("connection_count") or 0) - (first.get("connection_count") or 0),
            }
        return json.dumps({"report": report}, default=str)

    # ------------------------------------------------------------------
    # Knowledge
    # ------------------------------------------------------------------

    def _action_explore_platform(self, kw: dict) -> str:
        area = kw.get("area", "feed")
        _, creds = self._get_credentials(kw)

        guide_section = self._knowledge.get_guide("linkedin")
        task_desc = (
            f"Explore the LinkedIn '{area}' area. "
            "Navigate around, note UI elements, buttons, and behavior. "
            "Return observations as JSON: "
            '{"observations": [{"key": "...", "value": "...", "confidence": 0.8}]}.'
        )
        task = BrowserTask(
            task_description=(
                f"Log in with email '{creds['username']}' and password '{creds['password']}'. "
                + task_desc
            ),
            start_url="https://www.linkedin.com",
        )
        result_str = self._exec_browser(task, account_name=kw.get("account"))

        # Store observations as learnings
        try:
            data = json.loads(result_str)
            for obs in data.get("observations", []):
                self._knowledge.record_learning(
                    platform="linkedin",
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
            platform="linkedin", key=key, value=value, confidence=0.8,
        )
        return json.dumps({"recorded": True, "key": key})

    # ------------------------------------------------------------------
    # Account creation
    # ------------------------------------------------------------------

    def _action_create_account(self, kw: dict) -> str:
        first_name = kw.get("first_name")
        last_name = kw.get("last_name")
        email_account = kw.get("email_account")
        linkedin_password = kw.get("linkedin_password")

        if not all([first_name, last_name, email_account, linkedin_password]):
            return json.dumps({
                "error": "first_name, last_name, email_account, and linkedin_password are required",
            })

        if not self._email_store:
            return json.dumps({"error": "No email store configured — cannot create account"})

        email_acct = self._email_store.get(email_account)
        if not email_acct:
            return json.dumps({"error": f"Email account '{email_account}' not found"})

        email_address = email_acct["email_address"]

        task = self._adapter.build_signup_task(
            first_name=first_name,
            last_name=last_name,
            email_address=email_address,
            password=linkedin_password,
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
            safe_name = re.sub(r"[^a-z0-9-]", "", f"li-{first_name}-{last_name}".lower())
            account_id = self._store.add_account(
                name=safe_name,
                platform="linkedin",
                credentials={"username": email_address, "password": linkedin_password},
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
