"""Daemon lifecycle management: start, stop, and status for background agent."""

import os
import signal
import subprocess
import sys
import tempfile
import time


def read_pid(pid_path: str) -> int | None:
    """Read PID from file. Returns None if missing or invalid."""
    try:
        with open(pid_path) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def write_pid(pid_path: str, pid: int) -> None:
    """Atomically write PID to file."""
    dir_name = os.path.dirname(pid_path) or "."
    os.makedirs(dir_name, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(str(pid))
        os.replace(tmp, pid_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def remove_pid(pid_path: str) -> None:
    """Remove PID file if it exists."""
    try:
        os.unlink(pid_path)
    except FileNotFoundError:
        pass


def is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True


def start_daemon(pid_path: str, log_path: str) -> int:
    """Launch 'python -m src.main serve' as a detached background process.

    Returns the PID of the child process.

    Raises:
        RuntimeError: If the agent is already running.
    """
    existing_pid = read_pid(pid_path)
    if existing_pid is not None and is_process_alive(existing_pid):
        raise RuntimeError(
            f"Agent is already running (PID {existing_pid}). "
            f"Stop it first with: python -m src.main stop"
        )

    if existing_pid is not None:
        remove_pid(pid_path)

    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    log_file = open(log_path, "a", encoding="utf-8")

    kwargs: dict = {
        "stdout": log_file,
        "stderr": log_file,
        "stdin": subprocess.DEVNULL,
    }

    if sys.platform == "win32":
        DETACHED_PROCESS = 0x00000008
        CREATE_NO_WINDOW = 0x08000000
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        kwargs["creationflags"] = (
            DETACHED_PROCESS | CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [sys.executable, "-m", "src.main", "serve"],
        env=env,
        **kwargs,
    )

    write_pid(pid_path, proc.pid)
    return proc.pid


def stop_daemon(pid_path: str) -> int:
    """Stop the running agent daemon.

    Returns the PID that was stopped.

    Raises:
        RuntimeError: If no PID file exists or process is not running.
    """
    pid = read_pid(pid_path)
    if pid is None:
        raise RuntimeError(
            "No PID file found. Is the agent running? "
            "Check with: python -m src.main status"
        )

    if not is_process_alive(pid):
        remove_pid(pid_path)
        raise RuntimeError(
            f"PID file found (PID {pid}) but process is not running. "
            f"Stale PID file removed."
        )

    os.kill(pid, signal.SIGTERM)

    for _ in range(20):
        if not is_process_alive(pid):
            break
        time.sleep(0.1)
    else:
        if sys.platform != "win32":
            os.kill(pid, signal.SIGKILL)

    remove_pid(pid_path)
    return pid


def daemon_status(pid_path: str) -> tuple[str, int | None]:
    """Check daemon status.

    Returns:
        (status_message, pid_or_none)
    """
    pid = read_pid(pid_path)
    if pid is None:
        return "Agent is not running (no PID file).", None

    if is_process_alive(pid):
        return f"Agent is running (PID {pid}).", pid
    else:
        remove_pid(pid_path)
        return (
            f"Agent is not running (stale PID file for PID {pid} removed).",
            None,
        )
