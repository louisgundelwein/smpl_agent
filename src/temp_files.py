"""Temp file manager with TTL-based auto-cleanup."""

import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class TempFileManager:
    """Manages temporary files with automatic TTL-based cleanup.

    Scans the target directory periodically and deletes files
    older than ttl_hours. Runs cleanup in a daemon thread.
    """

    def __init__(
        self,
        directory: str,
        ttl_hours: int = 72,
        poll_interval: int = 3600,
    ) -> None:
        self._directory = Path(directory)
        self._ttl_seconds = ttl_hours * 3600
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._directory.mkdir(parents=True, exist_ok=True)

    @property
    def directory(self) -> Path:
        return self._directory

    def cleanup_once(self) -> int:
        """Run one cleanup pass. Returns count of deleted files."""
        if not self._directory.exists():
            return 0

        now = time.time()
        deleted = 0
        for entry in self._directory.iterdir():
            if not entry.is_file():
                # Also clean up empty session directories left by playwright
                if entry.is_dir():
                    try:
                        children = list(entry.iterdir())
                        if not children and (now - entry.stat().st_mtime) > self._ttl_seconds:
                            entry.rmdir()
                            deleted += 1
                            logger.info("Deleted expired empty dir: %s", entry.name)
                    except OSError:
                        pass
                continue
            age = now - entry.stat().st_mtime
            if age > self._ttl_seconds:
                try:
                    entry.unlink()
                    deleted += 1
                    logger.info("Deleted expired temp file: %s", entry.name)
                except OSError as exc:
                    logger.warning("Failed to delete %s: %s", entry.name, exc)
        return deleted

    def cleanup_loop(self) -> None:
        """Daemon thread target: periodic cleanup."""
        logger.info(
            "Temp file cleanup started (dir=%s, ttl=%dh, poll=%ds)",
            self._directory,
            self._ttl_seconds // 3600,
            self._poll_interval,
        )
        while not self._stop_event.is_set():
            try:
                self.cleanup_once()
            except Exception:
                logger.exception("Temp file cleanup error")
            self._stop_event.wait(self._poll_interval)

    def stop(self) -> None:
        """Signal the cleanup loop to stop."""
        self._stop_event.set()
