"""Tests for src.temp_files."""

import os
import time

import pytest

from src.temp_files import TempFileManager


@pytest.fixture
def manager(tmp_path):
    return TempFileManager(
        directory=str(tmp_path / "temp"),
        ttl_hours=1,
    )


def test_directory_created(manager):
    assert manager.directory.exists()


def test_cleanup_empty_dir(manager):
    assert manager.cleanup_once() == 0


def test_cleanup_deletes_old_files(manager):
    old_file = manager.directory / "old.webm"
    old_file.write_bytes(b"data")
    old_time = time.time() - 7200  # 2 hours ago (TTL is 1 hour)
    os.utime(old_file, (old_time, old_time))

    deleted = manager.cleanup_once()
    assert deleted == 1
    assert not old_file.exists()


def test_cleanup_preserves_recent_files(manager):
    new_file = manager.directory / "new.webm"
    new_file.write_bytes(b"data")

    deleted = manager.cleanup_once()
    assert deleted == 0
    assert new_file.exists()


def test_cleanup_mixed(manager):
    old = manager.directory / "old.webm"
    old.write_bytes(b"old")
    old_time = time.time() - 7200
    os.utime(old, (old_time, old_time))

    new = manager.directory / "new.webm"
    new.write_bytes(b"new")

    deleted = manager.cleanup_once()
    assert deleted == 1
    assert not old.exists()
    assert new.exists()


def test_cleanup_deletes_old_empty_dirs(manager):
    old_dir = manager.directory / "session_abc"
    old_dir.mkdir()
    old_time = time.time() - 7200
    os.utime(old_dir, (old_time, old_time))

    deleted = manager.cleanup_once()
    assert deleted == 1
    assert not old_dir.exists()


def test_cleanup_preserves_nonempty_dirs(manager):
    sub_dir = manager.directory / "session_xyz"
    sub_dir.mkdir()
    (sub_dir / "video.webm").write_bytes(b"video")
    old_time = time.time() - 7200
    os.utime(sub_dir, (old_time, old_time))

    deleted = manager.cleanup_once()
    assert deleted == 0
    assert sub_dir.exists()


def test_stop_event(manager):
    assert not manager._stop_event.is_set()
    manager.stop()
    assert manager._stop_event.is_set()
