"""Marketing tool: manage social media posts via browser automation."""

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from src.marketing.base import BrowserTask, PlatformAdapter
from src.marketing.instagram import InstagramAdapter
from src.marketing.linkedin import LinkedInAdapter
from src.marketing.reddit import RedditAdapter
from src.marketing.twitter import TwitterAdapter
from src.marketing_store import MarketingStore
from src.tools.base import Tool

logger = logging.getLogger(__name__)

_ADAPTERS: dict[str, PlatformAdapter] = {
    "reddit": RedditAdapter(),
    "twitter": TwitterAdapter(),
    "linkedin": LinkedInAdapter(knowledge=None),
    "instagram": InstagramAdapter(),
}


class MarketingTool(Tool):
    """Manage social media marketing: accounts, posts, metrics, comments.

    Uses browser-use for all platform interactions and the OpenAI-compatible
    endpoint for image generation.
    """

    def __init__(
        self,
        store: MarketingStore,
        openai_api_key: str,
        openai_model: str,
        openai_base_url: str | None = None,
        browser_timeout: int = 300,
    ) -> None:
        self._store = store
        self._openai_api_key = openai_api_key
        self._openai_model = openai_model
        self._openai_base_url = openai_base_url
        self._browser_timeout = browser_timeout

    def _run_async_task(self, coro: Any) -> Any:
        """Execute async task, handling existing event loops."""
        try:
            loop = asyncio.get_running_loop()
            # Event loop already running, use run_coroutine_threadsafe
            future = loop.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=self._browser_timeout)
        except RuntimeError:
            # No running event loop, use asyncio.run
            return asyncio.run(coro)

    @property
    def name(self) -> str:
        return "marketing"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Social media marketing automation. Manage platform accounts, "
                    "create and publish posts via browser, track engagement metrics, "
                    "read and reply to comments, and generate images. "
                    "Supports Reddit, Twitter/X, LinkedIn, and Instagram."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "add_account", "list_accounts", "remove_account",
                                "create_post", "list_posts", "get_post",
                                "fetch_metrics", "get_performance",
                                "get_comments", "reply_comment",
                                "delete_post", "get_recent_content",
                                "generate_image",
                            ],
                            "description": (
                                "The marketing action to perform."
                            ),
                        },
                        "name": {
                            "type": "string",
                            "description": "Account name (for add/remove account).",
                        },
                        "platform": {
                            "type": "string",
                            "enum": ["reddit", "twitter", "linkedin", "instagram"],
                            "description": "Social media platform.",
                        },
                        "credentials": {
                            "type": "object",
                            "description": "Login credentials (username, password, etc.).",
                        },
                        "config": {
                            "type": "object",
                            "description": "Platform-specific config (default subreddits, hashtags).",
                        },
                        "account": {
                            "type": "string",
                            "description": "Account name (for post/metrics operations).",
                        },
                        "content": {
                            "type": "string",
                            "description": "Post body text.",
                        },
                        "title": {
                            "type": "string",
                            "description": "Post title (Reddit, LinkedIn).",
                        },
                        "url": {
                            "type": "string",
                            "description": "Link to promote.",
                        },
                        "subreddit": {
                            "type": "string",
                            "description": "Target subreddit (Reddit only).",
                        },
                        "campaign": {
                            "type": "string",
                            "description": "Campaign name for grouping posts.",
                        },
                        "post_id": {
                            "type": "integer",
                            "description": "Post ID (for get/fetch/delete operations).",
                        },
                        "comment_id": {
                            "type": "string",
                            "description": "Comment ID to reply to.",
                        },
                        "body": {
                            "type": "string",
                            "description": "Reply body text.",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["draft", "posted", "failed", "deleted"],
                            "description": "Filter posts by status.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results to return (default: 20).",
                        },
                        "days": {
                            "type": "integer",
                            "description": "Time window for performance summary (default: 30).",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "Image generation prompt.",
                        },
                        "size": {
                            "type": "string",
                            "description": "Image size (default: 1024x1024).",
                        },
                        "generate_image_prompt": {
                            "type": "string",
                            "description": "If set, generate an image with this prompt and attach to post.",
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
        try:
            if action == "add_account":
                return self._add_account(kwargs)
            elif action == "list_accounts":
                return self._list_accounts()
            elif action == "remove_account":
                return self._remove_account(kwargs)
            elif action == "create_post":
                return self._create_post(kwargs)
            elif action == "list_posts":
                return self._list_posts(kwargs)
            elif action == "get_post":
                return self._get_post(kwargs)
            elif action == "fetch_metrics":
                return self._fetch_metrics(kwargs)
            elif action == "get_performance":
                return self._get_performance(kwargs)
            elif action == "get_comments":
                return self._get_comments(kwargs)
            elif action == "reply_comment":
                return self._reply_comment(kwargs)
            elif action == "delete_post":
                return self._delete_post(kwargs)
            elif action == "get_recent_content":
                return self._get_recent_content(kwargs)
            elif action == "generate_image":
                return self._generate_image_action(kwargs)
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    # ------------------------------------------------------------------
    # Account management
    # ------------------------------------------------------------------

    def _add_account(self, kw: dict) -> str:
        name = kw.get("name")
        platform = kw.get("platform")
        credentials = kw.get("credentials")
        if not all([name, platform, credentials]):
            return json.dumps({
                "error": "name, platform, and credentials are required"
            })
        if platform not in _ADAPTERS:
            return json.dumps({
                "error": f"Unsupported platform: {platform}. "
                         f"Supported: {', '.join(_ADAPTERS.keys())}"
            })
        acct_id = self._store.add_account(
            name=name,
            platform=platform,
            credentials=credentials,
            config=kw.get("config"),
        )
        return json.dumps({"added": True, "account_id": acct_id, "name": name})

    def _list_accounts(self) -> str:
        accts = self._store.list_accounts()
        return json.dumps({"accounts": accts, "count": len(accts)}, default=str)

    def _remove_account(self, kw: dict) -> str:
        name = kw.get("name")
        if not name:
            return json.dumps({"error": "name is required"})
        removed = self._store.remove_account(name)
        return json.dumps({"removed": removed, "name": name})

    # ------------------------------------------------------------------
    # Post creation
    # ------------------------------------------------------------------

    def _create_post(self, kw: dict) -> str:
        account_name = kw.get("account")
        content = kw.get("content")
        if not all([account_name, content]):
            return json.dumps({"error": "account and content are required"})

        acct = self._store.get_account(account_name)
        if not acct:
            return json.dumps({"error": f"Account '{account_name}' not found"})

        platform = acct["platform"]
        adapter = _ADAPTERS.get(platform)
        if not adapter:
            return json.dumps({"error": f"No adapter for platform: {platform}"})

        # Optional image generation
        image_path = None
        if kw.get("generate_image_prompt"):
            image_path = self._generate_image(kw["generate_image_prompt"],
                                              kw.get("size", "1024x1024"))

        # Store draft
        post_id = self._store.create_post(
            account_name=account_name,
            platform=platform,
            content=content,
            title=kw.get("title"),
            url=kw.get("url"),
            image_path=image_path,
            subreddit=kw.get("subreddit"),
            campaign=kw.get("campaign"),
        )

        # Build and execute browser task
        credentials = acct["credentials"]
        if isinstance(credentials, str):
            credentials = json.loads(credentials)

        browser_task = adapter.build_post_task(
            credentials=credentials,
            content=content,
            title=kw.get("title"),
            image_path=image_path,
            url=kw.get("url"),
            subreddit=kw.get("subreddit"),
        )

        try:
            result_str = self._run_async_task(self._run_browser_task(browser_task))
            # Try to parse the browser result for platform IDs
            platform_post_id = None
            try:
                result_data = json.loads(result_str)
                platform_post_id = (
                    result_data.get("url") or result_data.get("post_id")
                )
            except (json.JSONDecodeError, TypeError):
                platform_post_id = result_str

            self._store.update_post_status(
                post_id, "posted", platform_post_id=platform_post_id,
            )
            return json.dumps({
                "posted": True,
                "post_id": post_id,
                "platform_post_id": platform_post_id,
                "platform": platform,
            })
        except Exception as exc:
            self._store.update_post_status(post_id, "failed", error=str(exc))
            return json.dumps({
                "posted": False,
                "post_id": post_id,
                "error": str(exc),
            })

    # ------------------------------------------------------------------
    # Post queries
    # ------------------------------------------------------------------

    def _list_posts(self, kw: dict) -> str:
        posts = self._store.list_posts(
            account_name=kw.get("account"),
            platform=kw.get("platform"),
            campaign=kw.get("campaign"),
            status=kw.get("status"),
            limit=kw.get("limit", 20),
        )
        return json.dumps({"posts": posts, "count": len(posts)}, default=str)

    def _get_post(self, kw: dict) -> str:
        post_id = kw.get("post_id")
        if not post_id:
            return json.dumps({"error": "post_id is required"})
        post = self._store.get_post(post_id)
        if not post:
            return json.dumps({"error": f"Post {post_id} not found"})
        metrics = self._store.get_metrics(post_id)
        return json.dumps(
            {"post": post, "metrics": metrics}, default=str,
        )

    def _get_recent_content(self, kw: dict) -> str:
        content = self._store.get_recent_content(
            platform=kw.get("platform"),
            limit=kw.get("limit", 50),
        )
        return json.dumps({"recent_content": content, "count": len(content)})

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def _fetch_metrics(self, kw: dict) -> str:
        post_id = kw.get("post_id")
        if not post_id:
            return json.dumps({"error": "post_id is required"})

        post = self._store.get_post(post_id)
        if not post:
            return json.dumps({"error": f"Post {post_id} not found"})
        if not post.get("platform_post_id"):
            return json.dumps({"error": "Post has no platform ID (not yet posted?)"})

        acct = self._store.get_account(post["account_name"])
        if not acct:
            return json.dumps({"error": f"Account '{post['account_name']}' not found"})

        adapter = _ADAPTERS.get(post["platform"])
        if not adapter:
            return json.dumps({"error": f"No adapter for: {post['platform']}"})

        credentials = acct["credentials"]
        if isinstance(credentials, str):
            credentials = json.loads(credentials)

        browser_task = adapter.build_metrics_task(
            credentials=credentials,
            platform_post_id=post["platform_post_id"],
        )

        try:
            result_str = self._run_async_task(self._run_browser_task(browser_task))
            metrics_data = json.loads(result_str)
            metric_id = self._store.record_metrics(
                post_id=post_id,
                likes=metrics_data.get("likes", 0),
                comments=metrics_data.get("comments", 0),
                shares=metrics_data.get("shares", 0),
                views=metrics_data.get("views", 0),
                extra=metrics_data.get("extra"),
            )
            return json.dumps({
                "fetched": True,
                "metric_id": metric_id,
                "metrics": metrics_data,
            })
        except Exception as exc:
            return json.dumps({"error": f"Failed to fetch metrics: {exc}"})

    def _get_performance(self, kw: dict) -> str:
        summary = self._store.get_performance_summary(
            account_name=kw.get("account"),
            platform=kw.get("platform"),
            campaign=kw.get("campaign"),
            days=kw.get("days", 30),
        )
        return json.dumps({"performance": summary}, default=str)

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    def _get_comments(self, kw: dict) -> str:
        post_id = kw.get("post_id")
        if not post_id:
            return json.dumps({"error": "post_id is required"})

        post = self._store.get_post(post_id)
        if not post:
            return json.dumps({"error": f"Post {post_id} not found"})
        if not post.get("platform_post_id"):
            return json.dumps({"error": "Post has no platform ID"})

        acct = self._store.get_account(post["account_name"])
        if not acct:
            return json.dumps({"error": f"Account '{post['account_name']}' not found"})

        adapter = _ADAPTERS.get(post["platform"])
        if not adapter:
            return json.dumps({"error": f"No adapter for: {post['platform']}"})

        credentials = acct["credentials"]
        if isinstance(credentials, str):
            credentials = json.loads(credentials)

        browser_task = adapter.build_get_comments_task(
            credentials=credentials,
            platform_post_id=post["platform_post_id"],
            limit=kw.get("limit", 20),
        )

        try:
            result_str = self._run_async_task(self._run_browser_task(browser_task))
            return result_str
        except Exception as exc:
            return json.dumps({"error": f"Failed to get comments: {exc}"})

    def _reply_comment(self, kw: dict) -> str:
        post_id = kw.get("post_id")
        comment_id = kw.get("comment_id")
        body = kw.get("body")
        if not all([post_id, comment_id, body]):
            return json.dumps({
                "error": "post_id, comment_id, and body are required"
            })

        post = self._store.get_post(post_id)
        if not post:
            return json.dumps({"error": f"Post {post_id} not found"})

        acct = self._store.get_account(post["account_name"])
        if not acct:
            return json.dumps({"error": f"Account '{post['account_name']}' not found"})

        adapter = _ADAPTERS.get(post["platform"])
        if not adapter:
            return json.dumps({"error": f"No adapter for: {post['platform']}"})

        credentials = acct["credentials"]
        if isinstance(credentials, str):
            credentials = json.loads(credentials)

        browser_task = adapter.build_reply_task(
            credentials=credentials,
            platform_post_id=post["platform_post_id"],
            comment_id=comment_id,
            body=body,
        )

        try:
            result_str = self._run_async_task(self._run_browser_task(browser_task))
            return result_str
        except Exception as exc:
            return json.dumps({"error": f"Failed to reply: {exc}"})

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def _delete_post(self, kw: dict) -> str:
        post_id = kw.get("post_id")
        if not post_id:
            return json.dumps({"error": "post_id is required"})

        post = self._store.get_post(post_id)
        if not post:
            return json.dumps({"error": f"Post {post_id} not found"})

        if post.get("platform_post_id"):
            acct = self._store.get_account(post["account_name"])
            if acct:
                adapter = _ADAPTERS.get(post["platform"])
                if adapter:
                    credentials = acct["credentials"]
                    if isinstance(credentials, str):
                        credentials = json.loads(credentials)
                    browser_task = adapter.build_delete_task(
                        credentials=credentials,
                        platform_post_id=post["platform_post_id"],
                    )
                    try:
                        self._run_async_task(self._run_browser_task(browser_task))
                    except Exception as exc:
                        logger.warning("Browser delete failed: %s", exc)

        self._store.update_post_status(post_id, "deleted")
        return json.dumps({"deleted": True, "post_id": post_id})

    # ------------------------------------------------------------------
    # Image generation
    # ------------------------------------------------------------------

    def _generate_image(self, prompt: str, size: str = "1024x1024") -> str:
        """Generate image via DGPT and save locally. Returns local file path."""
        from openai import OpenAI

        client = OpenAI(
            api_key=self._openai_api_key,
            base_url=self._openai_base_url,
        )
        response = client.images.generate(prompt=prompt, size=size, n=1)
        image_url = response.data[0].url

        import httpx

        img_dir = Path("marketing_images")
        img_dir.mkdir(parents=True, exist_ok=True)
        local_path = str(img_dir / f"{uuid.uuid4().hex}.png")

        resp = httpx.get(image_url, timeout=60)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(resp.content)

        return local_path

    def _generate_image_action(self, kw: dict) -> str:
        prompt = kw.get("prompt")
        if not prompt:
            return json.dumps({"error": "prompt is required"})
        try:
            path = self._generate_image(prompt, kw.get("size", "1024x1024"))
            return json.dumps({"generated": True, "path": path})
        except Exception as exc:
            return json.dumps({"error": f"Image generation failed: {exc}"})

    # ------------------------------------------------------------------
    # Browser execution
    # ------------------------------------------------------------------

    async def _run_browser_task(self, task: BrowserTask) -> str:
        """Execute a browser-use task. Same pattern as BrowserTool."""
        from browser_use import Agent as BrowserAgent, Browser, BrowserConfig
        from langchain_openai import ChatOpenAI

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

        agent = BrowserAgent(task=full_task, llm=llm, browser=browser)

        try:
            result = await asyncio.wait_for(
                agent.run(),
                timeout=self._browser_timeout,
            )
        finally:
            await browser.close()

        return str(result)
