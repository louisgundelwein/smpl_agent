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
- **Conversation persistence** — conversation history survives restarts via atomic JSON file writes
- **Automatic context management** — long conversations are automatically compressed so the context window never fills up
- **Tool system** — add new tools in two steps: create a class, register it
- **Daemon mode** — run the agent as a background server, attach/detach without losing conversation
- **Telegram integration** — talk to your agent from Telegram with shared conversation history
- **223 tests** — full coverage, no real HTTP/LLM calls, fast

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

### Daemon / Telegram

| Variable | Required | Default | Description |
|---|---|---|---|
| `AGENT_HOST` | no | `127.0.0.1` | Daemon bind address |
| `AGENT_PORT` | no | `7600` | Daemon port |
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

### Telegram

1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Set `TELEGRAM_BOT_TOKEN` in `.env`
3. Optionally restrict access with `TELEGRAM_ALLOWED_CHAT_IDS`
4. Start the daemon: `python -m src.main serve`

The Telegram bot and CLI share the same conversation history.

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
├── config.py          # .env configuration loader
├── events.py          # Event system (LLM/Tool/Context lifecycle events)
├── formatting.py      # Event formatting for terminal display
├── protocol.py        # JSON-lines TCP protocol
├── server.py          # Daemon TCP server
├── client.py          # Attach client
├── telegram.py        # Telegram bot (long polling)
├── memory.py          # Semantic memory (SQLite + vector embeddings)
├── embeddings.py      # OpenAI embeddings wrapper
└── tools/
    ├── base.py        # Abstract Tool base class
    ├── registry.py    # Tool registration and dispatch
    ├── brave_search.py # Brave Web Search (1s rate limit)
    ├── shell.py       # Shell command execution
    ├── codex.py       # Codex CLI integration
    ├── github.py      # GitHub REST API integration
    └── memory_tool.py # Memory tool (store / search / delete)

tests/                 # Mirrors src/, 223 tests
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
- Dependencies: `openai`, `httpx`, `python-dotenv`, `numpy`
- Dev: `pytest`, `pytest-mock`, `respx`

## License

MIT
