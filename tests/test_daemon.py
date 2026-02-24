"""Tests for src.daemon — daemon lifecycle management."""

import os
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from src.daemon import (
    daemon_status,
    is_port_in_use,
    is_process_alive,
    read_pid,
    remove_pid,
    start_daemon,
    stop_daemon,
    write_pid,
)


# --- PID file management ---


class TestReadPid:
    def test_returns_none_for_missing_file(self, tmp_path):
        assert read_pid(str(tmp_path / "nonexistent.pid")) is None

    def test_returns_none_for_invalid_content(self, tmp_path):
        pid_file = tmp_path / "bad.pid"
        pid_file.write_text("not-a-number")
        assert read_pid(str(pid_file)) is None

    def test_returns_pid(self, tmp_path):
        pid_file = tmp_path / "test.pid"
        pid_file.write_text("12345")
        assert read_pid(str(pid_file)) == 12345


class TestWritePid:
    def test_write_and_read_roundtrip(self, tmp_path):
        pid_file = str(tmp_path / "test.pid")
        write_pid(pid_file, 42)
        assert read_pid(pid_file) == 42

    def test_creates_parent_directories(self, tmp_path):
        pid_file = str(tmp_path / "sub" / "dir" / "test.pid")
        write_pid(pid_file, 99)
        assert read_pid(pid_file) == 99


class TestRemovePid:
    def test_removes_existing_file(self, tmp_path):
        pid_file = tmp_path / "test.pid"
        pid_file.write_text("123")
        remove_pid(str(pid_file))
        assert not pid_file.exists()

    def test_no_error_if_missing(self, tmp_path):
        remove_pid(str(tmp_path / "nonexistent.pid"))


# --- Process alive check ---


class TestIsProcessAlive:
    def test_current_process_is_alive(self):
        assert is_process_alive(os.getpid()) is True

    def test_dead_pid_is_not_alive(self):
        # PID 4194304 is unlikely to be running (above typical PID range)
        assert is_process_alive(4194304) is False


# --- daemon_status ---


class TestDaemonStatus:
    def test_no_pid_file(self, tmp_path):
        msg, pid = daemon_status(str(tmp_path / "missing.pid"))
        assert "not running" in msg
        assert pid is None

    def test_stale_pid_cleaned(self, tmp_path):
        pid_file = tmp_path / "stale.pid"
        pid_file.write_text("4194304")
        msg, pid = daemon_status(str(pid_file))
        assert "not running" in msg
        assert "stale" in msg
        assert pid is None
        assert not pid_file.exists()

    def test_running_process(self, tmp_path):
        pid_file = tmp_path / "running.pid"
        pid_file.write_text(str(os.getpid()))
        msg, pid = daemon_status(str(pid_file))
        assert "running" in msg.lower()
        assert pid == os.getpid()


# --- start_daemon ---


class TestStartDaemon:
    def test_raises_if_already_running(self, tmp_path):
        pid_file = str(tmp_path / "test.pid")
        write_pid(pid_file, os.getpid())
        with pytest.raises(RuntimeError, match="already running"):
            start_daemon(pid_file, str(tmp_path / "test.log"))

    def test_raises_if_port_in_use(self, tmp_path, mocker):
        pid_file = str(tmp_path / "test.pid")
        log_file = str(tmp_path / "test.log")
        mocker.patch("src.daemon.is_port_in_use", return_value=True)
        with pytest.raises(RuntimeError, match="already in use"):
            start_daemon(pid_file, log_file)

    def test_cleans_stale_pid_and_starts(self, tmp_path, mocker):
        pid_file = str(tmp_path / "test.pid")
        log_file = str(tmp_path / "test.log")
        write_pid(pid_file, 4194304)  # stale PID

        mock_proc = MagicMock()
        mock_proc.pid = 99999
        mocker.patch("src.daemon.is_port_in_use", return_value=False)
        mock_popen = mocker.patch("src.daemon.subprocess.Popen", return_value=mock_proc)

        pid = start_daemon(pid_file, log_file)

        assert pid == 99999
        assert read_pid(pid_file) == 99999
        mock_popen.assert_called_once()

    def test_spawns_with_correct_args(self, tmp_path, mocker):
        pid_file = str(tmp_path / "test.pid")
        log_file = str(tmp_path / "test.log")

        mock_proc = MagicMock()
        mock_proc.pid = 55555
        mocker.patch("src.daemon.is_port_in_use", return_value=False)
        mock_popen = mocker.patch("src.daemon.subprocess.Popen", return_value=mock_proc)

        start_daemon(pid_file, log_file)

        args, kwargs = mock_popen.call_args
        assert args[0] == [sys.executable, "-m", "src.main", "serve"]
        assert kwargs["stdin"] == subprocess.DEVNULL
        if sys.platform == "win32":
            assert "creationflags" in kwargs
        else:
            assert kwargs["start_new_session"] is True


# --- stop_daemon ---


class TestStopDaemon:
    def test_raises_if_no_pid_file(self, tmp_path):
        with pytest.raises(RuntimeError, match="No PID file"):
            stop_daemon(str(tmp_path / "missing.pid"))

    def test_raises_if_stale_pid(self, tmp_path):
        pid_file = tmp_path / "stale.pid"
        pid_file.write_text("4194304")
        with pytest.raises(RuntimeError, match="not running"):
            stop_daemon(str(pid_file))
        assert not pid_file.exists()

    def test_kills_process_and_removes_pid(self, tmp_path, mocker):
        pid_file = str(tmp_path / "test.pid")
        write_pid(pid_file, 12345)

        call_count = 0

        def fake_alive(pid):
            nonlocal call_count
            call_count += 1
            return call_count <= 1  # alive on first check, dead after kill

        mocker.patch("src.daemon.is_process_alive", side_effect=fake_alive)
        mock_kill = mocker.patch("os.kill")

        result = stop_daemon(pid_file)

        assert result == 12345
        mock_kill.assert_called_once()
        assert read_pid(pid_file) is None
