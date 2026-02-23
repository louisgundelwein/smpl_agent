# Agent Project

Terminal-based AI agent with OpenAI LLM integration and tool calling.

## Project Structure

- `src/` - Main source code
  - `main.py` - Terminal REPL entry point
  - `agent.py` - Agentic loop (LLM <-> tool execution)
  - `llm.py` - OpenAI SDK wrapper
  - `config.py` - Configuration from .env
  - `tools/` - Tool system (base class, registry, implementations)
- `tests/` - pytest test suite

## Commands

- Install: `pip install -e ".[dev]"`
- Run: `python -m src.main`
- Test all: `pytest tests/ -v`
- Test single: `pytest tests/test_agent.py -v`

## Configuration

### LLM (OpenAI-compatible)
- `OPENAI_API_KEY` -- API Key (required)
- `OPENAI_MODEL` -- Model name (default: `gpt-4o`, e.g. `gemini-2.5-flash`)
- `OPENAI_BASE_URL` -- Custom endpoint (optional, e.g. `https://apiv2.deutschlandgpt.de/platform-api/api/v2`)

### Tools
- `BRAVE_SEARCH_API_KEY` -- Brave Search API key (required)

## Conventions

- Python 3.11+, type hints everywhere
- New tools: subclass `src.tools.base.Tool`, register in `src/main.py:create_agent()`
- Tools return JSON strings from `execute()`
- Tests use `pytest-mock` for mocking, `respx` for HTTP mocking
- API keys in `.env` (never committed), template in `.env.example`
