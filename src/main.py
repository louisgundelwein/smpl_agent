"""Terminal REPL entry point with daemon/attach support."""

import argparse
import os
import platform
import sys
from pathlib import Path

from src.agent import SYSTEM_PROMPT, Agent
from src.config import Config
from src.context import ContextManager
from src.db import Database
from src.events import AgentEvent, EventEmitter
from src.formatting import format_event
from src.history import ConversationHistory
from src.embeddings import EmbeddingClient
from src.llm import LLMClient
from src.memory import MemoryStore
from src.calendar_store import CalendarConnectionStore
from src.email_store import EmailAccountStore
from src.hyperliquid_store import HyperliquidStore
from src.repos import RepoStore
from src.scheduler import Scheduler, SchedulerStore
from src.subagent import SubagentManager
from src.tools import (
    BraveSearchTool,
    CalendarTool,
    CodexTool,
    EmailTool,
    GitHubTool,
    HyperliquidTool,
    MemoryTool,
    ReposTool,
    SchedulerTool,
    ShellTool,
    SubagentTool,
    ToolRegistry,
)


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


def _build_repo_context(repo_store: RepoStore) -> str:
    """Build a markdown list of known repos for the system prompt."""
    repos = repo_store.list_all()
    if not repos:
        return ""

    lines = ["\n\n## Known Repositories\n"]
    for repo in repos:
        tags = f" [{', '.join(repo['tags'])}]" if repo.get("tags") else ""
        desc = f" — {repo['description']}" if repo.get("description") else ""
        lines.append(
            f"- **{repo['name']}**: `{repo['owner']}/{repo['repo']}` "
            f"(branch: `{repo['default_branch']}`, url: `{repo['url']}`){desc}{tags}"
        )
    return "\n".join(lines)


def create_agent(
    config: Config,
    db: Database,
    scheduler_store: SchedulerStore | None = None,
    repo_store: RepoStore | None = None,
    calendar_store: CalendarConnectionStore | None = None,
    email_store: EmailAccountStore | None = None,
    hyperliquid_store: HyperliquidStore | None = None,
) -> Agent:
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
        dimensions=config.embedding_dimensions,
    )

    memory_store = MemoryStore(
        db=db,
        embedding_client=embedding_client,
        dimensions=config.embedding_dimensions,
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
    if scheduler_store:
        registry.register(SchedulerTool(store=scheduler_store))
    if repo_store:
        registry.register(ReposTool(store=repo_store))
    if calendar_store:
        registry.register(CalendarTool(store=calendar_store))
    if email_store:
        registry.register(EmailTool(store=email_store))
    if hyperliquid_store and config.hyperliquid_wallet_key and config.hyperliquid_wallet_address:
        registry.register(HyperliquidTool(
            store=hyperliquid_store,
            wallet_key=config.hyperliquid_wallet_key,
            wallet_address=config.hyperliquid_wallet_address,
            testnet=config.hyperliquid_testnet,
            max_position_size_usd=config.hyperliquid_max_position_usd,
            max_loss_usd=config.hyperliquid_max_loss_usd,
            max_leverage=config.hyperliquid_max_leverage,
        ))

    # Subagent system: factory creates isolated agents for subtasks
    emitter = EventEmitter()

    def _subagent_factory(task: str) -> Agent:
        sub_llm = LLMClient(
            api_key=config.openai_api_key,
            model=config.openai_model,
            base_url=config.openai_base_url,
        )
        sub_registry = ToolRegistry()
        sub_registry.register(BraveSearchTool(api_key=config.brave_search_api_key))
        sub_registry.register(ShellTool(
            command_timeout=config.shell_command_timeout,
            max_output=config.shell_max_output,
        ))
        if config.github_token:
            sub_registry.register(GitHubTool(
                token=config.github_token,
                max_output=config.shell_max_output,
            ))
        sub_prompt = (
            "You are a focused sub-agent working on a specific task. "
            "Complete the task thoroughly and return a clear, concise result. "
            "Do not ask clarifying questions — work with what you have."
        )
        return Agent(
            llm=sub_llm,
            registry=sub_registry,
            system_prompt=sub_prompt,
            max_tool_rounds=config.subagent_tool_rounds,
        )

    subagent_manager = SubagentManager(
        agent_factory=_subagent_factory,
        emitter=emitter,
        max_concurrent=config.max_subagents,
    )
    registry.register(SubagentTool(manager=subagent_manager))

    context_manager = ContextManager(
        llm=llm,
        max_tokens=config.context_max_tokens,
        preserve_recent=config.context_preserve_recent,
    )
    history = ConversationHistory(db)

    system_prompt = _load_system_prompt(config.soul_path) + _build_system_context()
    if repo_store:
        system_prompt += _build_repo_context(repo_store)

    return Agent(
        llm=llm,
        registry=registry,
        system_prompt=system_prompt,
        context_manager=context_manager,
        history=history,
        max_tool_rounds=config.max_tool_rounds,
        emitter=emitter,
        subagent_manager=subagent_manager,
    )


def repl(agent: Agent, db: Database) -> None:
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

    db.close()


def _load_static_tasks(scheduler_store: SchedulerStore, raw: str) -> None:
    """Load static scheduler tasks from SCHEDULER_TASKS JSON config.

    Each entry: {"name": ..., "prompt": ..., "schedule": ..., "deliver_to": ..., "telegram_chat_id": ...}
    Uses upsert to avoid duplicates on restart.
    """
    if not raw.strip():
        return
    import json

    try:
        tasks = json.loads(raw)
    except json.JSONDecodeError:
        print(f"Warning: SCHEDULER_TASKS is not valid JSON, skipping.", file=sys.stderr)
        return

    for task in tasks:
        name = task.get("name")
        prompt = task.get("prompt")
        schedule = task.get("schedule")
        if not all([name, prompt, schedule]):
            continue
        scheduler_store.upsert(
            name=name,
            prompt=prompt,
            cron_expression=schedule,
            deliver_to=task.get("deliver_to", "memory"),
            telegram_chat_id=task.get("telegram_chat_id"),
        )


def serve(config: Config) -> None:
    """Start the agent daemon server."""
    import signal as _signal

    from src.server import AgentServer
    from src.telegram import TelegramBot
    from src.transcription import Transcriber

    # Create shared database connection pool
    db = Database(config.database_url)

    # Create persistent stores
    scheduler_store = SchedulerStore(db=db)
    repo_store = RepoStore(db=db)
    calendar_store = CalendarConnectionStore(db=db)
    email_store = EmailAccountStore(db=db)
    hyperliquid_store = HyperliquidStore(db=db) if config.hyperliquid_wallet_key else None

    # Load static scheduled tasks from config
    _load_static_tasks(scheduler_store, config.scheduler_tasks)

    agent = create_agent(
        config,
        db=db,
        scheduler_store=scheduler_store,
        repo_store=repo_store,
        calendar_store=calendar_store,
        email_store=email_store,
        hyperliquid_store=hyperliquid_store,
    )
    agent.emitter.on(_print_event)

    telegram_bot = None
    telegram_send = None
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
            telegram_send = telegram_bot._send_message
        except Exception as exc:
            print(f"Telegram bot token invalid: {exc}", file=sys.stderr)
            db.close()
            sys.exit(1)

    scheduler = Scheduler(
        store=scheduler_store,
        telegram_send=telegram_send,
        poll_interval=config.scheduler_poll_interval,
    )

    server = AgentServer(
        agent=agent,
        host=config.agent_host,
        port=config.agent_port,
        telegram_bot=telegram_bot,
        scheduler=scheduler,
    )

    if sys.platform != "win32":
        def _handle_sigterm(signum, frame):
            db.close()
            server.shutdown()
        _signal.signal(_signal.SIGTERM, _handle_sigterm)

    try:
        server.serve_forever()
    finally:
        db.close()


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
        db = Database(config.database_url)
        scheduler_store = SchedulerStore(db=db)
        repo_store = RepoStore(db=db)
        calendar_store = CalendarConnectionStore(db=db)
        email_store = EmailAccountStore(db=db)
        hyperliquid_store = HyperliquidStore(db=db) if config.hyperliquid_wallet_key else None
        _load_static_tasks(scheduler_store, config.scheduler_tasks)
        agent = create_agent(
            config,
            db=db,
            scheduler_store=scheduler_store,
            repo_store=repo_store,
            calendar_store=calendar_store,
            email_store=email_store,
            hyperliquid_store=hyperliquid_store,
        )
        repl(agent, db)


if __name__ == "__main__":
    main()
