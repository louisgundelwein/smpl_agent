"""Abstract base for platform adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BrowserTask:
    """A browser automation task for a platform action."""

    task_description: str
    start_url: str | None = None


@dataclass
class PostResult:
    """Result of a platform posting action."""

    success: bool
    platform_post_id: str | None = None
    url: str | None = None
    error: str | None = None


class PlatformAdapter(ABC):
    """Generates browser task descriptions for a specific platform.

    Adapters don't make API calls — they construct natural-language
    task descriptions that browser-use executes.
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform identifier (e.g. 'reddit')."""
        ...

    @abstractmethod
    def build_post_task(
        self,
        credentials: dict[str, Any],
        content: str,
        title: str | None = None,
        image_path: str | None = None,
        **kwargs: Any,
    ) -> BrowserTask:
        """Build a browser task to create a post."""
        ...

    @abstractmethod
    def build_metrics_task(
        self,
        credentials: dict[str, Any],
        platform_post_id: str,
    ) -> BrowserTask:
        """Build a browser task to fetch engagement metrics."""
        ...

    @abstractmethod
    def build_get_comments_task(
        self,
        credentials: dict[str, Any],
        platform_post_id: str,
        limit: int = 20,
    ) -> BrowserTask:
        """Build a browser task to retrieve comments on a post."""
        ...

    @abstractmethod
    def build_reply_task(
        self,
        credentials: dict[str, Any],
        platform_post_id: str,
        comment_id: str,
        body: str,
    ) -> BrowserTask:
        """Build a browser task to reply to a comment."""
        ...

    @abstractmethod
    def build_delete_task(
        self,
        credentials: dict[str, Any],
        platform_post_id: str,
    ) -> BrowserTask:
        """Build a browser task to delete a post."""
        ...

    # ------------------------------------------------------------------
    # Optional extended methods (default: not supported)
    # ------------------------------------------------------------------

    def build_feed_browse_task(
        self, credentials: dict[str, Any], query: str | None = None, limit: int = 10,
    ) -> BrowserTask:
        raise NotImplementedError(f"{self.platform_name} does not support feed browsing")

    def build_like_task(self, credentials: dict[str, Any], post_url: str) -> BrowserTask:
        raise NotImplementedError(f"{self.platform_name} does not support liking")

    def build_comment_external_task(
        self, credentials: dict[str, Any], post_url: str, text: str,
    ) -> BrowserTask:
        raise NotImplementedError(f"{self.platform_name} does not support external comments")

    def build_repost_task(
        self, credentials: dict[str, Any], post_url: str, commentary: str | None = None,
    ) -> BrowserTask:
        raise NotImplementedError(f"{self.platform_name} does not support reposting")

    def build_connection_request_task(
        self, credentials: dict[str, Any], profile_url: str, note: str | None = None,
    ) -> BrowserTask:
        raise NotImplementedError(f"{self.platform_name} does not support connection requests")

    def build_accept_connections_task(self, credentials: dict[str, Any]) -> BrowserTask:
        raise NotImplementedError(f"{self.platform_name} does not support accepting connections")

    def build_send_message_task(
        self, credentials: dict[str, Any], recipient_url: str, message: str,
    ) -> BrowserTask:
        raise NotImplementedError(f"{self.platform_name} does not support messaging")

    def build_search_people_task(
        self, credentials: dict[str, Any], filters: dict[str, Any] | None = None,
    ) -> BrowserTask:
        raise NotImplementedError(f"{self.platform_name} does not support people search")

    def build_article_task(
        self, credentials: dict[str, Any], title: str, content: str,
    ) -> BrowserTask:
        raise NotImplementedError(f"{self.platform_name} does not support articles")

    def build_carousel_task(
        self, credentials: dict[str, Any], content: str, document_path: str,
    ) -> BrowserTask:
        raise NotImplementedError(f"{self.platform_name} does not support carousels")

    def build_poll_task(
        self, credentials: dict[str, Any], question: str, options: list[str],
    ) -> BrowserTask:
        raise NotImplementedError(f"{self.platform_name} does not support polls")

    def build_profile_analytics_task(self, credentials: dict[str, Any]) -> BrowserTask:
        raise NotImplementedError(f"{self.platform_name} does not support profile analytics")

    def build_ssi_score_task(self, credentials: dict[str, Any]) -> BrowserTask:
        raise NotImplementedError(f"{self.platform_name} does not support SSI score")
