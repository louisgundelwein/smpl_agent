"""Browser-use tool: perform web browser tasks via browser-use library."""

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from src.tools.base import Tool

logger = logging.getLogger(__name__)


class BrowserTool(Tool):
    """Execute browser automation tasks using the browser-use library.

    Each invocation spawns a headless browser, performs the task,
    records the session as a video, and returns the result with
    a path to the recording.
    """

    def __init__(
        self,
        openai_api_key: str,
        openai_model: str,
        openai_base_url: str | None = None,
        recording_dir: str = "browser_recordings",
        timeout: int = 300,
    ) -> None:
        self._openai_api_key = openai_api_key
        self._openai_model = openai_model
        self._openai_base_url = openai_base_url
        self._recording_dir = Path(recording_dir)
        self._timeout = timeout
        self._recording_dir.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "browser"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "browser",
                "description": (
                    "Perform a web browser task using an AI-controlled browser. "
                    "The browser can navigate websites, fill forms, click buttons, "
                    "extract information, and interact with web pages. "
                    "Each session is recorded as a video. "
                    "Use this for tasks that require a real browser "
                    "(e.g. interacting with web apps, scraping dynamic content, "
                    "filling out forms, taking actions on websites)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": (
                                "The browser task to perform. Be specific about "
                                "what website to visit and what actions to take."
                            ),
                        },
                        "url": {
                            "type": "string",
                            "description": (
                                "Optional starting URL. If provided, the browser "
                                "opens this URL before executing the task."
                            ),
                        },
                    },
                    "required": ["task"],
                },
            },
        }

    def execute(self, **kwargs: Any) -> str:
        task = kwargs.get("task")
        if not task:
            return json.dumps({"error": "Missing required parameter: task"})

        url = kwargs.get("url")

        try:
            result = asyncio.run(self._run_browser(task, url))
            return json.dumps(result)
        except ImportError as exc:
            return json.dumps({
                "error": (
                    f"browser-use not installed: {exc}. "
                    "Install with: pip install -e '.[browser]'"
                )
            })
        except asyncio.TimeoutError:
            return json.dumps({
                "error": f"Browser task timed out after {self._timeout}s"
            })
        except Exception as exc:
            logger.exception("Browser tool error")
            return json.dumps({"error": str(exc)})

    async def _run_browser(
        self, task: str, url: str | None
    ) -> dict[str, Any]:
        from browser_use import Agent as BrowserAgent, Browser, BrowserConfig
        from langchain_openai import ChatOpenAI

        session_id = uuid.uuid4().hex[:12]
        recording_path = str(self._recording_dir / f"session_{session_id}")

        browser_config = BrowserConfig(
            headless=True,
            save_recording_path=recording_path,
        )
        browser = Browser(config=browser_config)

        llm_kwargs: dict[str, Any] = {
            "model": self._openai_model,
            "api_key": self._openai_api_key,
        }
        if self._openai_base_url:
            llm_kwargs["base_url"] = self._openai_base_url
        llm = ChatOpenAI(**llm_kwargs)

        full_task = task
        if url:
            full_task = f"Go to {url}. Then: {task}"

        agent = BrowserAgent(
            task=full_task,
            llm=llm,
            browser=browser,
        )

        try:
            result = await asyncio.wait_for(
                agent.run(),
                timeout=self._timeout,
            )
        finally:
            await browser.close()

        actual_recording = self._find_recording(recording_path)

        response: dict[str, Any] = {
            "result": str(result),
            "session_id": session_id,
        }
        if actual_recording:
            response["recording_path"] = str(actual_recording)

        return response

    @staticmethod
    def _find_recording(recording_path: str) -> Path | None:
        """Find the recording file produced by browser-use/playwright."""
        path = Path(recording_path)
        if path.is_file():
            return path
        if path.is_dir():
            for ext in ("*.webm", "*.mp4", "*.avi"):
                files = sorted(path.glob(ext))
                if files:
                    return files[0]
        return None
