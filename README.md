# smpl_agent

A minimal, extensible AI agent that runs in your terminal. It connects to any OpenAI-compatible LLM, makes autonomous tool calls, and can run as a persistent daemon you attach/detach from — or talk to via Telegram.

## Features

- **Agentic loop** — the LLM decides when and which tools to use, executes them, feeds results back, and repeats until it has an answer
- **Any OpenAI-compatible provider** — swap models and endpoints via `.env` (OpenAI, DeutschlandGPT, Ollama, etc.)
- **Shell access** — the agent can run any command on your machine: read/write files, install packages, run scripts, inspect processes
- **Codex integration** — delegate complex coding tasks to OpenAI's Codex CLI for autonomous code writing, refactoring, and debugging
- **GitHub integration** — manage repos, issues, pull requests, and files via the GitHub REST API
- **Web search** — built-in Brave Search integration with source citations
- **Persistent memory** — semantic memory across sessions via SQLite + vector embeddings
- **Calendar management** — create, list, update, and delete events on any CalDAV server (Nextcloud, iCloud, Google Calendar)
- **Email** — read, search, and send emails via IMAP/SMTP (Gmail, Outlook, or any generic provider)
- **Scheduled tasks** — cron-based recurring tasks with delivery to memory or Telegram
- **Repository registry** — track known repos so the agent can find and work on them without asking
- **Subagents** — spawn concurrent background agents for parallel task execution
- **Voice messages** — send voice messages via Telegram, transcribed locally with Whisper
- **Customizable personality** — edit `SOUL.md` to change the agent's character, values, and communication style
- **Conversation persistence** — conversation history survives restarts via atomic JSON file writes
- **Automatic context management** — long conversations are automatically compressed so the context window never fills up
- **Tool system** — add new tools in two steps: create a class, register it
- **Daemon mode** — run the agent as a background server, attach/detach without losing conversation
- **Telegram integration** — talk to your agent from Telegram with shared conversation history
- **481 tests** — full coverage, no real HTTP/LLM calls, fast

## Quick Start

```bash
# Clone
git clone https://github.com/louisgundelwein/smpl_agent.git
cd smpl_agent

# Install
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run
python -m src.main
```

## Configuration

All config lives in `.env` (gitignored). Copy `.env.example` and fill in your keys:

### LLM

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | yes | — | API key for your LLM provider |
| `OPENAI_MODEL` | no | `gpt-4o` | Model name |
| `OPENAI_BASE_URL` | no | — | Custom endpoint for non-OpenAI providers |

### Tools

| Variable | Required | Default | Description |
|---|---|---|---|
| `BRAVE_SEARCH_API_KEY` | yes | — | [Brave Search API](https://brave.com/search/api/) key |
| `SHELL_COMMAND_TIMEOUT` | no | `30` | Max seconds a shell command may run |
| `SHELL_MAX_OUTPUT` | no | `50000` | Max characters captured from stdout/stderr |

### Memory

| Variable | Required | Default | Description |
|---|---|---|---|
| `EMBEDDING_MODEL` | no | `text-embedding-3-large` | OpenAI embedding model for semantic search |
| `MEMORY_DB_PATH` | no | `agent_memory.db` | Path to the SQLite memory database |

### Codex

| Variable | Required | Default | Description |
|---|---|---|---|
| `CODEX_TIMEOUT` | no | `300` | Max seconds for a Codex execution |
| `CODEX_MAX_OUTPUT` | no | `50000` | Max characters in Codex output |

### GitHub

| Variable | Required | Default | Description |
|---|---|---|---|
| `GITHUB_TOKEN` | no | — | GitHub personal access token ([create one](https://github.com/settings/tokens)) |

### Context Management

| Variable | Required | Default | Description |
|---|---|---|---|
| `CONTEXT_MAX_TOKENS` | no | `100000` | Token threshold that triggers compression |
| `CONTEXT_PRESERVE_RECENT` | no | `10` | Last N messages that are never compressed |

### Conversation History

| Variable | Required | Default | Description |
|---|---|---|---|
| `HISTORY_PATH` | no | `conversation_history.json` | Path to the conversation history file |

### Scheduled Tasks

| Variable | Required | Default | Description |
|---|---|---|---|
| `SCHEDULER_DB_PATH` | no | `scheduler.db` | SQLite database for scheduled tasks |
| `SCHEDULER_POLL_INTERVAL` | no | `30` | Seconds between scheduler polls |
| `SCHEDULER_TASKS` | no | — | Static tasks as JSON array, loaded on startup (see [Scheduled Tasks](#scheduled-tasks)) |

### Repository Registry

| Variable | Required | Default | Description |
|---|---|---|---|
| `REPOS_DB_PATH` | no | `repos.db` | SQLite database for known repositories |

### Calendar (CalDAV)

| Variable | Required | Default | Description |
|---|---|---|---|
| `CALENDAR_DB_PATH` | no | `calendar.db` | SQLite database for CalDAV connections |

### Email (IMAP/SMTP)

| Variable | Required | Default | Description |
|---|---|---|---|
| `EMAIL_DB_PATH` | no | `email.db` | SQLite database for email accounts |

### Subagents

| Variable | Required | Default | Description |
|---|---|---|---|
| `MAX_SUBAGENTS` | no | `10` | Maximum concurrent subagents |
| `SUBAGENT_TOOL_ROUNDS` | no | `15` | Max tool rounds per subagent |

### Voice Transcription

| Variable | Required | Default | Description |
|---|---|---|---|
| `WHISPER_MODEL` | no | `openai/whisper-large-v3-turbo` | HuggingFace Whisper model ID |

Dependencies (`torch`, `transformers`, `accelerate`, `imageio-ffmpeg`) are auto-installed on first voice message. Pre-install with `pip install -e ".[transcription]"` to avoid the first-use delay.

### Personality

| Variable | Required | Default | Description |
|---|---|---|---|
| `SOUL_PATH` | no | `SOUL.md` | Path to the agent's personality/system-prompt file |

Edit `SOUL.md` to change the agent's name, communication style, values, and behavior.

### Daemon / Telegram

| Variable | Required | Default | Description |
|---|---|---|---|
| `AGENT_HOST` | no | `127.0.0.1` | Daemon bind address |
| `AGENT_PORT` | no | `7600` | Daemon port |
| `DAEMON_PID_PATH` | no | `agent.pid` | PID file location |
| `DAEMON_LOG_PATH` | no | `agent.log` | Log file location |
| `TELEGRAM_BOT_TOKEN` | no | — | Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_ALLOWED_CHAT_IDS` | no | — | Comma-separated chat IDs (empty = allow all) |

### Custom LLM Provider Example

```env
OPENAI_BASE_URL=https://apiv2.deutschlandgpt.de/platform-api/api/v2
OPENAI_MODEL=gemini-2.5-flash
OPENAI_API_KEY=your-key
```

## Usage

### Direct REPL

```bash
python -m src.main
```

Interactive terminal session. LLM calls and tool executions are logged inline with timing:

```
You: What is the current weather in Berlin?
  [llm] round 1 (2 messages, ~312 tokens)
  [llm] done (tool calls, 1843ms)
  [tool] brave_web_search(query='current weather Berlin')
  [tool] done (245ms)
  [llm] round 2 (5 messages, ~1820 tokens)
  [llm] done (response, 2105ms)

Agent: Based on my search, Berlin currently has...
```

Commands: `reset` (clear history), `quit` / `exit` (leave).

Conversation history is automatically saved to `conversation_history.json`. When you restart the agent, it picks up right where you left off. Use `reset` to start a fresh conversation.

### Daemon Mode

Start the agent as a persistent background server:

```bash
python -m src.main serve
```

Attach from another terminal:

```bash
python -m src.main attach
```

Detach with `quit` — the agent keeps running and retains the full conversation. Reattach anytime.

Manage the daemon:

```bash
python -m src.main status   # check if the daemon is running
python -m src.main stop     # stop the daemon
```

View live logs:

```bash
tail -f agent.log
```

The log path is configurable via `DAEMON_LOG_PATH` in `.env` (default: `agent.log`).

### Telegram

1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Set `TELEGRAM_BOT_TOKEN` in `.env`
3. Optionally restrict access with `TELEGRAM_ALLOWED_CHAT_IDS`
4. Start the daemon: `python -m src.main serve`

The Telegram bot and CLI share the same conversation history. You can send text messages, voice messages (transcribed via Whisper), and use swipe-to-reply to give the agent context from previous messages.

Long responses are automatically split into multiple messages to stay within Telegram's 4096-character limit.

## Shell Access

The agent has full shell access via the `shell` tool. It can run any command available in your terminal:

```
You: Find all Python files modified in the last 7 days
  [tool] shell(command='find . -name "*.py" -mtime -7')
  [tool] done

Agent: I found 4 recently modified files: ...
```

```
You: Install the requests library and test it
  [tool] shell(command='pip install requests')
  [tool] done
  [tool] shell(command='python -c "import requests; print(requests.__version__)"')
  [tool] done

Agent: Successfully installed requests 2.31.0.
```

Long outputs are automatically trimmed (first 1 000 + last N chars with a notice in between) so the context window is not flooded by a single command.

Be careful with destructive operations — the agent is instructed to confirm before anything irreversible.

## Codex Integration

The agent can delegate complex coding tasks to [Codex](https://github.com/openai/codex), OpenAI's CLI tool for autonomous coding. This requires a ChatGPT subscription.

### Prerequisites

```bash
npm install -g @openai/codex

# Desktop (opens browser):
codex login

# Headless server (shows a code to enter on another device):
codex login --device-code
```

No API key needed — Codex uses OAuth and stores credentials in `~/.codex/auth.json`.

### How it works

When the agent receives a coding task it can't handle well on its own, it delegates to Codex via the `codex` tool:

```
You: Build a REST API with FastAPI that has CRUD endpoints for a todo app
  [tool] codex(prompt='Build a REST API with FastAPI...')
  [tool] done

Agent: Codex created the following files: ...
```

Under the hood, the agent pipes the prompt to `codex exec --json -` as a subprocess. Codex autonomously reads files, writes code, runs commands, and returns the result.

For simple file operations (`cat`, `echo >`, `ls`) the `shell` tool is more efficient. Codex is best for multi-file, multi-step coding tasks.

## GitHub Integration

The agent can interact with the GitHub REST API via the `github` tool. Set `GITHUB_TOKEN` in `.env` to enable it.

### Setup

1. Create a [personal access token](https://github.com/settings/tokens) with the scopes you need (e.g. `repo`, `read:org`)
2. Set `GITHUB_TOKEN` in `.env`

The tool is a generic API wrapper — the agent can call any GitHub endpoint:

```
You: List my open pull requests in the smpl_agent repo
  [tool] github(method='GET', endpoint='/repos/louisgundelwein/smpl_agent/pulls', params={'state': 'open'})
  [tool] done

Agent: You have 2 open pull requests: ...
```

```
You: Create an issue about the memory leak bug
  [tool] github(method='POST', endpoint='/repos/louisgundelwein/smpl_agent/issues', body={'title': 'Memory leak in long sessions', 'body': '...'})
  [tool] done

Agent: Created issue #42: Memory leak in long sessions
```

If `GITHUB_TOKEN` is not set, the tool is simply not registered — no error, no crash.

## Scheduled Tasks

The agent can run tasks automatically on a cron schedule via the `scheduler` tool. Useful for recurring checks, reports, or maintenance.

```
You: Check my open PRs every morning at 9am and send the results to Telegram
  [tool] scheduler(action='create', name='daily-prs', prompt='Check open PRs on all my repos', schedule='0 9 * * *', deliver_to='telegram', telegram_chat_id=12345)
  [tool] done

Agent: Created scheduled task "daily-prs". It will run daily at 9:00 UTC.
```

### Schedule formats

- **Cron expressions**: `0 9 * * *` (daily at 9am), `*/30 * * * *` (every 30 minutes), `0 0 * * 1` (Monday midnight)
- **Simple intervals**: `every 6h`, `every 30m`, `every 1d`

All times are UTC.

### Delivery

Results can be delivered to:
- `memory` (default) — stored in the agent's persistent memory
- `telegram` — sent to a Telegram chat (requires `telegram_chat_id`)
- `both` — stored in memory and sent to Telegram

### Management

```
You: Show me all scheduled tasks
  [tool] scheduler(action='list')

You: Disable the daily-prs task
  [tool] scheduler(action='disable', name='daily-prs')

You: Delete it
  [tool] scheduler(action='delete', name='daily-prs')
```

Static tasks can be pre-loaded via the `SCHEDULER_TASKS` environment variable:

```env
SCHEDULER_TASKS=[{"name":"daily-prs","prompt":"Check open PRs","schedule":"0 9 * * *","deliver_to":"telegram","telegram_chat_id":12345}]
```

## Repository Registry

The agent maintains a list of known repositories via the `repos` tool. When you mention a repo or ask the agent to work on one, it checks its registry first — no need to repeat URLs or branch names.

```
You: Remember the smpl_agent repo
  [tool] repos(action='add', name='smpl_agent', owner='louisgundelwein', repo='smpl_agent', url='https://github.com/louisgundelwein/smpl_agent.git', default_branch='main')
  [tool] done

Agent: Registered smpl_agent.
```

```
You: What repos do I have?
  [tool] repos(action='list')

Agent: You have 3 repos registered: smpl_agent, my-website, data-pipeline.
```

Each repo stores: name, GitHub owner/repo, clone URL, default branch, description, and tags. The agent uses this when cloning, creating branches, or opening PRs.

## Calendar Management

The agent can manage calendars and events via the `calendar` tool using the CalDAV protocol. It works with Nextcloud, iCloud, Google Calendar, and any CalDAV-compatible server.

### Setup

Register a CalDAV connection first:

```
You: Connect to my Nextcloud calendar
  [tool] calendar(action='add_connection', name='nextcloud', url='https://cloud.example.com/remote.php/dav', username='alice', password='app-password', provider='nextcloud')
  [tool] done

Agent: Connected to your Nextcloud CalDAV server.
```

### Working with events

```
You: What's on my calendar this week?
  [tool] calendar(action='list_events', connection='nextcloud', calendar='Personal', start='2026-02-23T00:00:00', end='2026-03-02T00:00:00')

You: Schedule a meeting tomorrow at 10am
  [tool] calendar(action='create_event', connection='nextcloud', calendar='Personal', summary='Team standup', start='2026-02-26T10:00:00', end='2026-02-26T10:30:00', reminder_minutes=15)

You: Move that meeting to 2pm
  [tool] calendar(action='update_event', connection='nextcloud', calendar='Personal', uid='...', start='2026-02-26T14:00:00', end='2026-02-26T14:30:00')
```

Events support: `summary`, `start`, `end`, `description`, `location`, `reminder_minutes`. Update and delete events by their `uid`.

## Email

The agent can read, search, and send emails via the `email` tool using IMAP (reading) and SMTP (sending). It works with Gmail, Outlook, and any generic IMAP/SMTP provider using app-specific passwords.

### Setup

Register an email account:

```
You: Add my Gmail account
  [tool] email(action='add_account', name='gmail', email_address='alice@gmail.com', password='app-password', imap_host='imap.gmail.com', smtp_host='smtp.gmail.com')
  [tool] done

Agent: Added Gmail account.
```

For Gmail, you need an [app-specific password](https://myaccount.google.com/apppasswords) (not your regular password).

### Reading emails

```
You: Show me my latest unread emails
  [tool] email(action='read_emails', account='gmail', limit=10, unread_only=true)

You: Read that email from Bob in full
  [tool] email(action='read_email', account='gmail', uid='12345')
```

### Searching

```
You: Find emails from my boss since January
  [tool] email(action='search_emails', account='gmail', from_='boss@company.com', date_from='2026-01-01')
```

Search criteria: `from_`, `to`, `subject`, `text`, `seen`, `date_from`, `date_to`.

### Sending

```
You: Send Bob a quick email about the meeting
  [tool] email(action='send_email', account='gmail', to='bob@company.com', subject='Meeting tomorrow', body='Hi Bob, just a reminder about our meeting at 2pm.')

Agent: Email sent to bob@company.com.
```

### Management

- `mark_read` — mark an email as read by UID
- `move_email` — move an email to a different folder by UID
- `delete_email` — delete an email by UID
- `list_folders` — list available mailbox folders

## Subagents

The agent can spawn concurrent subagents that work on subtasks in parallel via the `subagent` tool. Each subagent is an independent agent with its own conversation, running in a background thread.

```
You: Research the top 3 Python web frameworks and compare them
  [tool] subagent(action='spawn', task='Research FastAPI: features, performance, community size, pros and cons')
  [subagent] spawned a1b2c3d4: Research FastAPI...
  [tool] subagent(action='spawn', task='Research Django: features, performance, community size, pros and cons')
  [subagent] spawned e5f6g7h8: Research Django...
  [tool] subagent(action='spawn', task='Research Flask: features, performance, community size, pros and cons')
  [subagent] spawned i9j0k1l2: Research Flask...
```

Later, the agent checks status and collects results:

```
  [tool] subagent(action='status')
  [tool] subagent(action='result', subagent_id='a1b2c3d4')
  [subagent] a1b2c3d4 → completed
```

### How it works

- Each subagent gets its own fresh `Agent` instance with access to web search, shell, and GitHub tools
- Subagents run independently and cannot spawn further subagents (no recursion)
- Tasks must be self-contained — subagents have no access to the main conversation context
- Up to 10 subagents can run concurrently (configurable via `MAX_SUBAGENTS`)
- Each subagent has a separate tool round limit (configurable via `SUBAGENT_TOOL_ROUNDS`)

### Actions

- `spawn` — create a subagent with a task description
- `status` — check progress of all or a specific subagent
- `result` — get the output of a completed subagent
- `cancel` — stop a running subagent

## Voice Messages

When running as a Telegram bot, the agent can receive and transcribe voice messages using a local [Whisper](https://huggingface.co/openai/whisper-large-v3-turbo) model.

1. Send a voice message in Telegram
2. The agent downloads the audio and transcribes it locally
3. The transcription is passed to the agent as `[Voice message transcription]: ...`
4. The agent responds normally

Transcription dependencies (`torch`, `transformers`, `accelerate`, `imageio-ffmpeg`) are auto-installed on first use. Pre-install them to avoid the delay:

```bash
pip install -e ".[transcription]"
```

The Whisper model is configurable via `WHISPER_MODEL` (default: `openai/whisper-large-v3-turbo`).

## Automatic Context Management

In long sessions, the conversation history grows quickly — especially when tool outputs are large (a single shell command can produce 50 000 characters). Without management, the LLM's context window fills up and the API starts rejecting requests.

**smpl_agent compresses automatically.** Before every LLM call, it estimates the total token count of the current message history. If it exceeds the configured limit, it summarizes the older part of the conversation:

```
You: [long conversation with many tool calls ...]
  [context] compressed: 33 messages removed (~95000 → ~28000 tokens)
  [tool] shell(...)
```

### How it works

The history is split into three zones:

```
[ System Prompt ]  +  [ compressible zone ]  +  [ last 10 messages ]
      ↓                        ↓                         ↓
 always kept          summarized by the LLM          always kept
```

The compressible zone is sent to the LLM with a prompt:

> *Summarize concisely. Preserve: key facts, decisions made, tool results that matter, user preferences. Omit: verbose tool outputs, repeated information.*

The resulting summary is injected back as a system message:

```
[Conversation Summary]
- User asked to set up the project, shell confirmed Python 3.11 installed
- Ran pip install, all dependencies resolved successfully
- User prefers concise answers without extra explanation
[End of Summary - Recent conversation follows]
```

**Tool-call pairs are never split** — an assistant message with tool calls and its corresponding tool results always stay together as one unit.

**Graceful degradation** — if the summarization call itself fails, the original messages are returned unchanged. No crash.

### Token estimation

Tokens are estimated as `total characters ÷ 4` (no external tokenizer dependency). This is deliberately conservative — it may compress slightly earlier than strictly necessary, but never too late.

### Tuning

```env
CONTEXT_MAX_TOKENS=100000   # Lower → more aggressive compression
CONTEXT_PRESERVE_RECENT=10  # Higher → more recent context guaranteed intact
```

## Adding a Tool

1. Create `src/tools/my_tool.py`:

```python
from src.tools.base import Tool

class MyTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "my_tool",
                "description": "Does something useful",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input": {"type": "string", "description": "The input"}
                    },
                    "required": ["input"],
                },
            },
        }

    def execute(self, **kwargs) -> str:
        return f"Result for: {kwargs['input']}"
```

2. Register in `src/main.py`:

```python
registry.register(MyTool())
```

That's it. The agent will automatically see the tool and use it when appropriate.

## Project Structure

```
src/
├── main.py            # CLI entry point (repl / serve / attach)
├── agent.py           # Agentic loop (LLM ↔ tool execution)
├── context.py         # Automatic context compression
├── history.py         # Conversation history persistence
├── llm.py             # Thin OpenAI SDK wrapper
├── embeddings.py      # OpenAI embeddings wrapper
├── config.py          # .env configuration loader
├── events.py          # Event system (LLM/Tool/Context/Subagent lifecycle)
├── formatting.py      # Event formatting for terminal display
├── protocol.py        # JSON-lines TCP protocol
├── server.py          # Daemon TCP server
├── client.py          # Attach client
├── daemon.py          # Background daemon lifecycle (start/stop/status)
├── telegram.py        # Telegram bot (long polling, voice messages)
├── transcription.py   # Whisper speech-to-text (lazy load)
├── memory.py          # Semantic memory (SQLite + vector embeddings)
├── scheduler.py       # Scheduled task engine (cron, SQLite persistence)
├── repos.py           # Repository registry (SQLite persistence)
├── calendar_store.py  # CalDAV connection registry (SQLite persistence)
├── email_store.py     # Email account registry (SQLite persistence)
├── subagent.py        # Subagent manager (concurrent background threads)
└── tools/
    ├── base.py         # Abstract Tool base class
    ├── registry.py     # Tool registration and dispatch
    ├── brave_search.py # Brave Web Search
    ├── shell.py        # Shell command execution
    ├── codex.py        # Codex CLI integration
    ├── github.py       # GitHub REST API
    ├── memory.py       # Semantic memory (store / search / delete)
    ├── scheduler.py    # Scheduled task management
    ├── repos.py        # Repository registry management
    ├── calendar.py     # CalDAV calendar and event management
    ├── email.py        # IMAP/SMTP email management
    └── subagent.py     # Subagent spawning and control

tests/                  # Mirrors src/, 481 tests
SOUL.md                 # Agent personality and system prompt
```

## Testing

```bash
# All tests
pytest tests/ -v

# Single file
pytest tests/test_agent.py -v
```

All tests are fully mocked (no real HTTP/LLM calls) and run in under 10 seconds.

## Requirements

- Python 3.11+
- Dependencies: `openai`, `httpx`, `python-dotenv`, `numpy`, `croniter`, `caldav`, `imap-tools`
- Dev: `pytest`, `pytest-mock`, `respx`
- Optional (voice): `torch`, `transformers`, `accelerate`, `imageio-ffmpeg`

## License

MIT
