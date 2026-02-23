"""Terminal REPL entry point."""

import sys

from src.config import Config
from src.llm import LLMClient
from src.tools import BraveSearchTool, ToolRegistry
from src.agent import Agent


def create_agent(config: Config) -> Agent:
    """Wire up all components and return a configured Agent."""
    llm = LLMClient(
        api_key=config.openai_api_key,
        model=config.openai_model,
        base_url=config.openai_base_url,
    )

    registry = ToolRegistry()
    registry.register(BraveSearchTool(api_key=config.brave_search_api_key))

    return Agent(llm=llm, registry=registry)


def main() -> None:
    """Run the terminal REPL loop."""
    try:
        config = Config.from_env()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    agent = create_agent(config)
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


if __name__ == "__main__":
    main()
