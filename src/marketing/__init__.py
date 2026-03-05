"""Marketing platform adapters."""

from src.marketing.base import BrowserTask, PlatformAdapter, PostResult
from src.marketing.reddit import RedditAdapter
from src.marketing.twitter import TwitterAdapter
from src.marketing.linkedin import LinkedInAdapter
from src.marketing.instagram import InstagramAdapter
from src.marketing.platform_knowledge import PlatformKnowledge

__all__ = [
    "BrowserTask",
    "PlatformAdapter",
    "PlatformKnowledge",
    "PostResult",
    "RedditAdapter",
    "TwitterAdapter",
    "LinkedInAdapter",
    "InstagramAdapter",
]
