"""Terminal REPL entry point with daemon/attach support."""

import argparse
import os
import platform
import sys
from pathlib import Path

from src.agent import SYSTEM_PROMPT, Agent
from src.config import Config
from src.context import ContextManager
from src.history import ConversationHistory
from src.events import AgentEvent
from src.formatting import format_event
from src.embeddings import EmbeddingClient
from src.llm import LLMClient
from src.memory import MemoryStore
from src.tools import BraveSearchTool, CodexTool, GitHubTool, MemoryTool, ShellTool, ToolRegistry


def _print_event(event: AgentEvent) -> None:
    """Default event handler: print agent events to terminal."""
    line = format_event(event)
    if line is not None:
        print(line)


def _load_system_prompt(soul_path: str) -> str:
    """Load system prompt from SOUL.md, falling back to the default if not found."""
    try:
        with open(soul_path, encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            return content
    except FileNotFoundError:
        pass
    return SYSTEM_PROMPT


def _build_system_context() -> str:
    """Auto-detect OS, shell, and directory context for the system prompt."""
    system = platform.system()
    release = platform.release()

    if system == "Windows":
        shell = os.environ.get("COMSPEC", "cmd.exe")
    else:
        shell = os.environ.get("SHELL", "/bin/sh")
    shell_name = Path(shell).name

    cwd = os.getcwd()
    home = str(Path.home())

    os_label = f"macOS {release}" if system == "Darwin" else f"{system} {release}"

    return (
        "\n\n## Environment\n\n"
        f"- OS: {os_label}\n"
        f"- Shell: {shell_name}\n"
        f"- Working directory: {cwd}\n"
        f"- Home directory: {home}"
    )


def create_agent(config: Config) -> Agent:
    """Wire up all components and return a configured Agent."""
    llm = LLMClient(
        api_key=config.openai_api_key,
        model=config.openai_model,
        base_url=config.openai_base_url,
    )

    embedding_client = EmbeddingClient(
        api_key=config.openai_api_key,
        model=config.embedding_model,
        base_url=config.openai_base_url,
    )

    memory_store = MemoryStore(
        db_path=config.memory_db_path,
        embedding_client=embedding_client,
    )

    registry = ToolRegistry()
    registry.register(BraveSearchTool(api_key=config.brave_search_api_key))
    registry.register(MemoryTool(memory_store=memory_store))
    registry.register(ShellTool(
        command_timeout=config.shell_command_timeout,
        max_output=config.shell_max_output,
    ))
    registry.register(CodexTool(
        timeout=config.codex_timeout,
        max_output=config.codex_max_output,
    ))
    if config.github_token:
        registry.register(GitHubTool(
            token=config.github_token,
            max_output=config.shell_max_output,
        ))
    context_manager = ContextManager(
        llm=llm,
        max_tokens=config.context_max_tokens,
        preserve_recent=config.context_preserve_recent,
    )
    history = ConversationHistory(config.history_path)
    system_prompt = _load_system_prompt(config.soul_path) + _build_system_context()
    return Agent(
        llm=llm,
        registry=registry,
        system_prompt=system_prompt,
        context_manager=context_manager,
        history=history,
    )


def repl(agent: Agent) -> None:
    """Run the direct terminal REPL loop (no server)."""
    agent.emitter.on(_print_event)

    print("Agent ready. Type 'quit' or 'exit' to leave. 'reset' to clear history.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Goodbye.")
            break
        if user_input.lower() == "reset":
            agent.reset()
            print("Conversation reset.\n")
            continue

        try:
            response = agent.run(user_input)
            print(f"\nAgent: {response}\n")
        except Exception as exc:
            print(f"\nError: {exc}\n", file=sys.stderr)


def serve(config: Config) -> None:
    """Start the agent daemon server."""
    import signal as _signal

    from src.server import AgentServer
    from src.telegram import TelegramBot
    from src.transcription import Transcriber

    agent = create_agent(config)
    agent.emitter.on(_print_event)

    telegram_bot = None
    if config.telegram_bot_token:
        transcriber = Transcriber(model_name=config.whisper_model)
        telegram_bot = TelegramBot(
            token=config.telegram_bot_token,
            allowed_chat_ids=config.telegram_allowed_chat_ids,
            transcriber=transcriber,
        )
        try:
            bot_name = telegram_bot.verify()
            print(f"Telegram bot verified: @{bot_name}")
        except Exception as exc:
            print(f"Telegram bot token invalid: {exc}", file=sys.stderr)
            sys.exit(1)

    server = AgentServer(
        agent=agent,
        host=config.agent_host,
        port=config.agent_port,
        telegram_bot=telegram_bot,
    )

    if sys.platform != "win32":
        def _handle_sigterm(signum, frame):
            server.shutdown()
        _signal.signal(_signal.SIGTERM, _handle_sigterm)

    server.serve_forever()


def attach(config: Config) -> None:
    """Connect to a running agent server."""
    from src.client import AgentClient

    client = AgentClient(host=config.agent_host, port=config.agent_port)
    try:
        client.repl()
    except ConnectionRefusedError:
        print(
            f"Could not connect to agent at {config.agent_host}:{config.agent_port}",
            file=sys.stderr,
        )
        print(
            "Is the server running? Start it with: python -m src.main serve",
            file=sys.stderr,
        )
        sys.exit(1)


def start(config: Config) -> None:
    """Start the agent server as a detached background process."""
    from src.daemon import start_daemon

    try:
        pid = start_daemon(
            config.daemon_pid_path,
            config.daemon_log_path,
            host=config.agent_host,
            port=config.agent_port,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Agent started in background (PID {pid}).")
    print(f"  Log: {config.daemon_log_path}")
    print(f"  PID file: {config.daemon_pid_path}")
    print(f"  Attach with: python -m src.main attach")
    print(f"  Stop with: python -m src.main stop")


def stop(config: Config) -> None:
    """Stop the background agent server."""
    from src.daemon import stop_daemon

    try:
        pid = stop_daemon(config.daemon_pid_path)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Agent stopped (PID {pid}).")


def status(config: Config) -> None:
    """Check the status of the background agent server."""
    from src.daemon import daemon_status

    message, _pid = daemon_status(config.daemon_pid_path)
    print(message)


def main() -> None:
    """CLI entry point with subcommands."""
    parser = argparse.ArgumentParser(
        prog="agent",
        description="Terminal AI agent with tool calling",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("serve", help="Start the agent daemon server")
    subparsers.add_parser("attach", help="Connect to a running agent server")
    subparsers.add_parser("start", help="Start the agent server in the background")
    subparsers.add_parser("stop", help="Stop the background agent server")
    subparsers.add_parser("status", help="Check if the agent server is running")

    args = parser.parse_args()

    try:
        config = Config.from_env()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.command == "serve":
        serve(config)
    elif args.command == "attach":
        attach(config)
    elif args.command == "start":
        start(config)
    elif args.command == "stop":
        stop(config)
    elif args.command == "status":
        status(config)
    else:
        agent = create_agent(config)
        repl(agent)


if __name__ == "__main__":
    main()
