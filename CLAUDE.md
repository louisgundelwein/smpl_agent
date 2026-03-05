# Agent Project

Terminal-based AI agent with OpenAI-compatible LLM integration and agentic tool calling.

## Project Structure

- `SOUL.md` - Agent personality and system prompt (edit to customise the agent's character)
- `src/` - Main source code
  - `main.py` - Terminal REPL entry point, wires all components together
  - `agent.py` - Agentic loop (LLM <-> tool execution cycle)
  - `llm.py` - OpenAI SDK wrapper (thin, swap-friendly)
  - `embeddings.py` - OpenAI Embeddings API wrapper (thin, mirrors llm.py)
  - `config.py` - Configuration from `.env`
  - `memory.py` - Semantic memory store (SQLite + numpy vector search)
  - `context.py` - Automatic context compression (LLM-based summarization)
  - `history.py` - Conversation history persistence (JSON file, atomic writes)
  - `events.py` - Event types and emitter for agent lifecycle notifications
  - `formatting.py` - Event formatting for terminal display (shared by REPL and client)
  - `protocol.py` - JSON-lines TCP protocol for daemon mode
  - `server.py` - Daemon TCP server
  - `client.py` - Attach client
  - `daemon.py` - Background daemon lifecycle (start, stop, status, PID management)
  - `telegram.py` - Telegram bot (long polling, voice message support)
  - `transcription.py` - Whisper speech-to-text (lazy dependency install, lazy model load)
  - `scheduler.py` - Scheduled task engine (SQLite persistence, cron parsing, polling loop)
  - `repos.py` - Repository registry (SQLite persistence, tracks known repos)
  - `calendar_store.py` - CalDAV connection registry (SQLite persistence)
  - `email_store.py` - Email account registry (SQLite persistence, IMAP/SMTP credentials)
  - `tools/` - Tool system
    - `base.py` - Abstract `Tool` base class (the contract every tool must follow)
    - `registry.py` - `ToolRegistry`: registers tools, provides schemas to LLM, dispatches calls
    - `brave_search.py` - Brave Web Search implementation
    - `memory.py` - Semantic memory tool (store, search, delete)
    - `shell.py` - Shell command execution tool
    - `codex.py` - Codex CLI integration (delegates coding tasks)
    - `github.py` - GitHub REST API integration
    - `scheduler.py` - Scheduler tool (create, list, delete, enable, disable scheduled tasks)
    - `repos.py` - Repos tool (add, list, remove, get, update known repositories)
    - `calendar.py` - Calendar tool (CalDAV: manage connections, calendars, events, reminders)
    - `email.py` - Email tool (IMAP/SMTP: manage accounts, read/search/send emails)
    - `subagent.py` - Subagent tool (spawn, status, result, cancel concurrent subagents)
  - `subagent.py` - Subagent manager (concurrent task execution via background threads)
- `tests/` - pytest test suite mirroring `src/` structure

## Commands

- Install: `pip install -e ".[dev]"`
- Run: `python -m src.main`
- Start background: `python -m src.main start`
- Stop background: `python -m src.main stop`
- Check status: `python -m src.main status`
- Test all: `pytest tests/ -v`
- Test single file: `pytest tests/test_agent.py -v`

## Configuration

All configuration comes from `.env` (never committed). See `.env.example` for the template.

### LLM (OpenAI-compatible)
- `OPENAI_API_KEY` -- API Key (required)
- `OPENAI_MODEL` -- Model name (default: `gpt-4o`, e.g. `gemini-2.5-flash`)
- `OPENAI_BASE_URL` -- Custom endpoint (optional, e.g. `https://apiv2.deutschlandgpt.de/platform-api/api/v2`)

### Tools
- `BRAVE_SEARCH_API_KEY` -- Brave Search API key (required)

### Memory
- `EMBEDDING_MODEL` -- Embedding model (default: `text-embedding-3-large`)
- `MEMORY_DB_PATH` -- SQLite database path (default: `agent_memory.db`)

### Soul
- `SOUL_PATH` -- Path to the soul/system-prompt file (default: `SOUL.md`)

### Shell
- `SHELL_COMMAND_TIMEOUT` -- Shell command timeout in seconds (default: `30`)
- `SHELL_MAX_OUTPUT` -- Max characters in shell output before truncation (default: `50000`)

### Context Management
- `CONTEXT_MAX_TOKENS` -- Estimated token limit before auto-compression (default: `100000`)
- `CONTEXT_PRESERVE_RECENT` -- Number of recent messages to always keep intact (default: `10`)

### Codex
- `CODEX_TIMEOUT` -- Max seconds for a Codex execution (default: `300`)
- `CODEX_MAX_OUTPUT` -- Max characters in Codex output before truncation (default: `50000`)

### GitHub
- `GITHUB_TOKEN` -- GitHub personal access token (optional, enables `github` tool)

### History
- `HISTORY_PATH` -- Path to conversation history file (default: `conversation_history.json`)

### Whisper Transcription
- `WHISPER_MODEL` -- HuggingFace model ID (default: `openai/whisper-large-v3-turbo`)
- Dependencies (`torch`, `transformers`, `accelerate`, `imageio-ffmpeg`) are auto-installed on first voice message
- Pre-install with `pip install -e ".[transcription]"` to avoid first-use delay
- Audio decoding uses `imageio-ffmpeg` bundled binary (no system ffmpeg install needed)

### Scheduler (Recurring Tasks)
- `SCHEDULER_DB_PATH` -- SQLite database path (default: `scheduler.db`)
- `SCHEDULER_POLL_INTERVAL` -- Seconds between scheduler polls (default: `30`)
- `SCHEDULER_TASKS` -- Static tasks as JSON array, loaded on startup via upsert (default: empty)
  - Format: `[{"name":"daily-prs","prompt":"Check open PRs","schedule":"0 9 * * *","deliver_to":"telegram","telegram_chat_id":12345}]`

### Repository Registry
- `REPOS_DB_PATH` -- SQLite database path (default: `repos.db`)

### Calendar (CalDAV)
- `CALENDAR_DB_PATH` -- SQLite database path for CalDAV connections (default: `calendar.db`)

### Email (IMAP/SMTP)
- `EMAIL_DB_PATH` -- SQLite database path for email accounts (default: `email.db`)

### Auto-Continuation
- `AGENT_MAX_CONTINUATIONS` -- Max continuation nudges per run() call (default: `20`, set `0` to disable)

### Subagents
- `MAX_SUBAGENTS` -- Maximum concurrent subagents (default: `10`)
- `SUBAGENT_TOOL_ROUNDS` -- Max tool rounds per subagent (default: `15`)

### Daemon
- `DAEMON_PID_PATH` -- PID file location (default: `agent.pid`)
- `DAEMON_LOG_PATH` -- Log file location (default: `agent.log`)

---

## Development Principles

### Architecture: keep modules small and single-purpose

Each module has exactly one job:
- `config.py` loads config — nothing else
- `llm.py` wraps the OpenAI SDK — nothing else
- `registry.py` manages tool registration and dispatch — nothing else
- `agent.py` runs the loop — nothing else

Do not let responsibilities bleed across modules. If a module is growing, that's a signal to split it.

### The agent loop is the core

`agent.py:Agent.run()` is the heart of the project. Its logic must stay simple and explicit:

1. Append user message
2. Call LLM with current messages + tool schemas
3. If the LLM returns text → return it (done)
4. If the LLM returns tool calls → execute each, append results, go to step 2
5. If `max_tool_rounds` is exceeded → raise `RuntimeError`

Do not add hidden state, side effects, or special-casing inside the loop. Any new agentic behavior (retries, memory, multi-agent) should be introduced as a clearly named layer, not silently woven into the loop.

### Tools are self-contained units

Every tool must:
- Inherit from `src.tools.base.Tool`
- Define its own OpenAI function-calling schema via the `schema` property
- Accept only `**kwargs` in `execute()` and return a `str`
- Handle its own errors internally where possible (return an error JSON string rather than raising)
- Implement rate limiting or retries internally — the agent loop should not know about these details

Adding a new tool requires exactly two steps:
1. Create `src/tools/<name>.py` with a class that subclasses `Tool`
2. Register it in `src/main.py:create_agent()` with `registry.register(...)`

Nothing else should need to change.

### LLM is a replaceable dependency

`LLMClient` is intentionally thin. It has no business logic — only the API call. This makes it easy to:
- Swap models via `.env` (no code changes)
- Swap providers by pointing `OPENAI_BASE_URL` at any OpenAI-compatible endpoint
- Mock it completely in tests with a few lines

Do not add model-specific logic to `LLMClient`. If a specific model needs special handling, do it in `Agent` or in a subclass.

### Tests are a first-class requirement

Every new feature or tool gets tests. The test structure mirrors `src/`:
- `tests/test_agent.py` covers the loop logic
- `tests/test_<toolname>.py` covers each tool

**Testing rules:**
- Never make real HTTP requests in tests — use `respx` to mock `httpx` calls
- Never make real LLM calls in tests — mock `LLMClient.chat`
- Use `pytest-mock`'s `mocker` fixture for patching, not bare `unittest.mock.patch` where avoidable
- Tests should be fast (< 2s total). Slow tests indicate a missing mock.
- A feature is not done until its tests pass.

### Terminal output: minimal and informative

The terminal shows:
- `You:` prompt for input
- `  [llm] round N (M messages, ~T tokens)` when an LLM call starts
- `  [llm] done (tool calls|response, Xms)` when it finishes
- `  [tool] <name>(<args>)` when a tool call starts
- `  [tool] done (Xms)` or `  [tool] error: <msg> (Xms)` when it finishes
- `  [context] compressed: ...` when context compression triggers
- `  [subagent] spawned <id>: <task>` when a subagent is created
- `  [subagent] <id> → <status>` when a subagent's status changes
- `Agent:` for the final response

All formatting lives in `src/formatting.py` (single source of truth for REPL and client). Do not add progress spinners, colors, or rich formatting unless explicitly requested. Keep the output predictable so it's easy to parse when testing or piping.

### Never commit secrets

API keys belong exclusively in `.env` (gitignored). The `.env.example` contains only placeholder strings. If a key is accidentally added to any tracked file, rotate it immediately at the provider.
