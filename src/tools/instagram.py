"""Dedicated Instagram tool: feed, content, stories, analytics, image generation."""

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from src.marketing.base import BrowserTask
from src.marketing.instagram import InstagramAdapter
from src.marketing.platform_knowledge import PlatformKnowledge
from src.marketing_store import MarketingStore
from src.tools.base import Tool

logger = logging.getLogger(__name__)


class InstagramTool(Tool):
    """Full Instagram integration: feed browsing, content creation, stories,
    interactions, DMs, follower management, analytics, and image generation.

    All platform interactions go through browser-use via the InstagramAdapter.
    Platform knowledge (static guide + dynamic learnings) is injected into
    every browser task for improved reliability.
    """

    def __init__(
        self,
        store: MarketingStore,
        knowledge: PlatformKnowledge,
        adapter: InstagramAdapter,
        openai_api_key: str,
        openai_model: str,
        openai_base_url: str | None = None,
        timeout: int = 300,
        action_delay: int = 5,
        browser_profiles_dir: str = "browser_profiles",
        email_store: "Any | None" = None,
        image_gen_base_url: str | None = None,
        image_gen_api_key: str | None = None,
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
        self._image_gen_base_url = image_gen_base_url
        self._image_gen_api_key = image_gen_api_key

    @property
    def name(self) -> str:
        return "instagram"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "instagram",
                "description": (
                    "Instagram platform tool. Browse feed and hashtags, create posts "
                    "(photo/carousel/reel), create stories, like/unlike, comment, "
                    "manage followers, send DMs, track analytics, generate images, "
                    "and manage drafts. All actions use browser automation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "create_account",
                                "browse_feed", "browse_hashtag", "search",
                                "create_post", "create_story", "delete_post",
                                "like", "unlike", "comment", "reply_to_comment",
                                "send_message", "read_inbox",
                                "follow_user", "unfollow_user", "list_followers", "list_following",
                                "get_post_performance", "get_profile_analytics", "get_analytics_report",
                                "save_draft", "list_drafts", "publish_draft",
                                "explore_platform", "record_learning",
                                "generate_image",
                            ],
                        },
                        "account": {
                            "type": "string",
                            "description": "Registered Instagram account name.",
                        },
                        "post_url": {
                            "type": "string",
                            "description": "URL of an Instagram post.",
                        },
                        "comment_id": {
                            "type": "string",
                            "description": "Comment identifier for reply_to_comment.",
                        },
                        "content": {
                            "type": "string",
                            "description": "Text content for captions, comments, messages.",
                        },
                        "caption": {
                            "type": "string",
                            "description": "Caption for posts (alias for content).",
                        },
                        "title": {
                            "type": "string",
                            "description": "Title prefix for captions or drafts.",
                        },
                        "query": {
                            "type": "string",
                            "description": "Search query.",
                        },
                        "hashtag": {
                            "type": "string",
                            "description": "Hashtag to browse (with or without #).",
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
                            "enum": ["photo", "carousel", "reel"],
                            "description": "Type of post to create.",
                        },
                        "image_path": {
                            "type": "string",
                            "description": "Path to image for photo posts or stories.",
                        },
                        "image_paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Paths to images for carousel posts (up to 10).",
                        },
                        "video_path": {
                            "type": "string",
                            "description": "Path to video for reels or stories.",
                        },
                        "generate_image_prompt": {
                            "type": "string",
                            "description": "AI image generation prompt. If provided with create_post, generates and attaches the image.",
                        },
                        "location": {
                            "type": "string",
                            "description": "Location to tag on a post.",
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
                        "area": {
                            "type": "string",
                            "description": "Platform area to explore (feed, stories, messaging).",
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
                            "description": "Extra metadata for drafts.",
                        },
                        "username": {
                            "type": "string",
                            "description": "Username for account creation or follow/unfollow.",
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
        if action == "generate_image":
            try:
                return self._action_generate_image(kwargs)
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
        if acct["platform"] != "instagram":
            raise ValueError(f"Account '{account_name}' is not an Instagram account")
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
        )
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_browse_hashtag(self, kw: dict) -> str:
        hashtag = kw.get("hashtag")
        if not hashtag:
            return json.dumps({"error": "hashtag is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_hashtag_browse_task(
            creds, hashtag, limit=kw.get("limit", 10),
        )
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_search(self, kw: dict) -> str:
        query = kw.get("query")
        if not query:
            return json.dumps({"error": "query is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_search_task(
            creds, query, limit=kw.get("limit", 10),
        )
        return self._exec_browser(task, account_name=kw.get("account"))

    # ------------------------------------------------------------------
    # Interactions
    # ------------------------------------------------------------------

    def _action_like(self, kw: dict) -> str:
        post_url = kw.get("post_url")
        if not post_url:
            return json.dumps({"error": "post_url is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_like_task(creds, post_url)
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_unlike(self, kw: dict) -> str:
        post_url = kw.get("post_url")
        if not post_url:
            return json.dumps({"error": "post_url is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_unlike_task(creds, post_url)
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
        post_type = kw.get("post_type", "photo")
        content = kw.get("content") or kw.get("caption")
        _, creds = self._get_credentials(kw)

        # Auto-generate image if prompt is provided
        image_path = kw.get("image_path")
        if kw.get("generate_image_prompt") and not image_path:
            gen_result = self._generate_image(kw["generate_image_prompt"])
            if gen_result.get("error"):
                return json.dumps({"error": f"Image generation failed: {gen_result['error']}"})
            image_path = gen_result.get("path")

        if post_type == "reel":
            video_path = kw.get("video_path")
            if not video_path:
                return json.dumps({"error": "video_path is required for reels"})
            task = self._adapter.build_post_task(
                creds, content or "", title=kw.get("title"),
                post_type="reel", video_path=video_path,
                location=kw.get("location"),
            )
        elif post_type == "carousel":
            image_paths = kw.get("image_paths")
            if not image_paths or len(image_paths) < 2:
                return json.dumps({"error": "image_paths with at least 2 images is required for carousel"})
            task = self._adapter.build_post_task(
                creds, content or "", title=kw.get("title"),
                post_type="carousel", image_paths=image_paths,
                location=kw.get("location"),
            )
        else:
            if not image_path:
                return json.dumps({"error": "image_path is required for photo posts (Instagram requires an image)"})
            task = self._adapter.build_post_task(
                creds, content or "", title=kw.get("title"),
                image_path=image_path, location=kw.get("location"),
            )

        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_create_story(self, kw: dict) -> str:
        _, creds = self._get_credentials(kw)
        image_path = kw.get("image_path")
        video_path = kw.get("video_path")
        text = kw.get("content")
        if not image_path and not video_path and not text:
            return json.dumps({"error": "image_path, video_path, or content is required for stories"})
        task = self._adapter.build_story_task(
            creds, image_path=image_path, video_path=video_path, text=text,
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
    # Follower management
    # ------------------------------------------------------------------

    def _action_follow_user(self, kw: dict) -> str:
        username = kw.get("username")
        if not username:
            return json.dumps({"error": "username is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_follow_task(creds, username)
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_unfollow_user(self, kw: dict) -> str:
        username = kw.get("username")
        if not username:
            return json.dumps({"error": "username is required"})
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_unfollow_task(creds, username)
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_list_followers(self, kw: dict) -> str:
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_list_followers_task(creds, limit=kw.get("limit", 50))
        return self._exec_browser(task, account_name=kw.get("account"))

    def _action_list_following(self, kw: dict) -> str:
        _, creds = self._get_credentials(kw)
        task = self._adapter.build_list_following_task(creds, limit=kw.get("limit", 50))
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

    def _action_get_profile_analytics(self, kw: dict) -> str:
        acct, creds = self._get_credentials(kw)
        task = self._adapter.build_profile_analytics_task(creds)
        result_str = self._exec_browser(task, account_name=kw.get("account"))

        try:
            data = json.loads(result_str)
            self._store.record_instagram_profile_metrics(
                account_id=acct["id"],
                followers=data.get("followers"),
                following=data.get("following"),
                posts_count=data.get("posts_count"),
                engagement_rate=data.get("engagement_rate"),
            )
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Could not store Instagram profile metrics: %s", exc)

        return result_str

    def _action_get_analytics_report(self, kw: dict) -> str:
        acct, _ = self._get_credentials(kw)
        days = kw.get("days", 30)
        history = self._store.get_instagram_profile_metrics_history(acct["id"], days=days)
        if not history:
            return json.dumps({
                "report": "No Instagram profile metrics recorded yet. "
                "Use get_profile_analytics first to collect data.",
                "days": days,
            })
        latest = history[-1]
        report = {
            "days": days,
            "data_points": len(history),
            "latest": {
                "followers": latest.get("followers"),
                "following": latest.get("following"),
                "posts_count": latest.get("posts_count"),
                "engagement_rate": latest.get("engagement_rate"),
                "recorded_at": str(latest.get("recorded_at")),
            },
        }
        if len(history) >= 2:
            first = history[0]
            report["growth"] = {
                "followers_change": (latest.get("followers") or 0) - (first.get("followers") or 0),
                "following_change": (latest.get("following") or 0) - (first.get("following") or 0),
                "posts_count_change": (latest.get("posts_count") or 0) - (first.get("posts_count") or 0),
            }
        return json.dumps({"report": report}, default=str)

    # ------------------------------------------------------------------
    # Drafts
    # ------------------------------------------------------------------

    def _action_save_draft(self, kw: dict) -> str:
        content = kw.get("content") or kw.get("caption")
        if not content:
            return json.dumps({"error": "content is required"})
        acct, _ = self._get_credentials(kw)
        draft_id = self._store.create_draft(
            account_id=acct["id"],
            content=content,
            post_type=kw.get("post_type", "photo"),
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

        if post_type == "reel":
            task = self._adapter.build_post_task(
                creds, draft["content"], title=draft.get("title"),
                post_type="reel", video_path=metadata.get("video_path"),
                location=metadata.get("location"),
            )
        elif post_type == "carousel":
            task = self._adapter.build_post_task(
                creds, draft["content"], title=draft.get("title"),
                post_type="carousel", image_paths=metadata.get("image_paths"),
                location=metadata.get("location"),
            )
        else:
            task = self._adapter.build_post_task(
                creds, draft["content"], title=draft.get("title"),
                image_path=metadata.get("image_path"),
                location=metadata.get("location"),
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
            f"Explore the Instagram '{area}' area. "
            "Navigate around, note UI elements, buttons, and behavior. "
            "Return observations as JSON: "
            '{"observations": [{"key": "...", "value": "...", "confidence": 0.8}]}.'
        )
        task = BrowserTask(
            task_description=(
                f"Log in with username '{creds['username']}' and password '{creds['password']}'. "
                + task_desc
            ),
            start_url="https://www.instagram.com",
        )
        result_str = self._exec_browser(task, account_name=kw.get("account"))

        try:
            data = json.loads(result_str)
            for obs in data.get("observations", []):
                self._knowledge.record_learning(
                    platform="instagram",
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
            platform="instagram", key=key, value=value, confidence=0.8,
        )
        return json.dumps({"recorded": True, "key": key})

    # ------------------------------------------------------------------
    # Image generation
    # ------------------------------------------------------------------

    def _generate_image(self, prompt: str) -> dict[str, Any]:
        """Generate an image using OpenAI-compatible images.generate API.

        Returns dict with 'path' on success or 'error' on failure.
        """
        import base64
        from openai import OpenAI

        api_key = self._image_gen_api_key or self._openai_api_key
        base_url = self._image_gen_base_url or self._openai_base_url

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)

        response = client.images.generate(
            prompt=prompt,
            n=1,
            size="1024x1024",
            response_format="b64_json",
        )

        image_data = response.data[0].b64_json
        if not image_data:
            return {"error": "No image data returned"}

        images_dir = Path("marketing_images")
        images_dir.mkdir(parents=True, exist_ok=True)

        timestamp = int(time.time())
        filename = f"ig_{timestamp}.png"
        filepath = images_dir / filename

        filepath.write_bytes(base64.b64decode(image_data))
        return {"path": str(filepath)}

    def _action_generate_image(self, kw: dict) -> str:
        prompt = kw.get("content") or kw.get("generate_image_prompt")
        if not prompt:
            return json.dumps({"error": "content or generate_image_prompt is required"})
        result = self._generate_image(prompt)
        if result.get("error"):
            return json.dumps({"error": result["error"]})
        return json.dumps({"generated": True, "path": result["path"]})

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
            safe_name = re.sub(r"[^a-z0-9-]", "", f"ig-{username}".lower())
            account_id = self._store.add_account(
                name=safe_name,
                platform="instagram",
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
