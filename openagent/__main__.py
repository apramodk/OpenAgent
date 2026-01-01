"""Entry point for OpenAgent CLI."""

import asyncio
import sys

from openagent.server.jsonrpc import JSONRPCServer


def main() -> None:
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        run_server()
    else:
        run_cli()


def run_server() -> None:
    """Run the JSON-RPC server for TUI communication."""
    from pathlib import Path
    from openagent.server.handlers import create_handlers

    # Ensure data directory exists
    db_path = Path.home() / ".local/share/openagent/sessions.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    server = JSONRPCServer()
    handlers = create_handlers(db_path)
    server.register_all(handlers)

    # Notify TUI that server is ready
    server.notify_sync("server.ready", {"version": "0.1.0"})
    asyncio.run(server.run())


def run_cli() -> None:
    """Run interactive CLI mode."""
    from openagent.core.agent import Agent, AgentConfig

    print("OpenAgent CLI v0.1.0")
    print("Type 'quit' or 'exit' to stop.\n")

    config = AgentConfig(
        system_prompt="You are a helpful AI assistant for understanding codebases.",
    )
    agent = Agent(config=config)

    while True:
        try:
            user_input = input("\033[32muser:\033[0m ")

            if user_input.lower() in ("quit", "exit", "q"):
                print("Goodbye!")
                break

            if not user_input.strip():
                continue

            response = agent.chat_sync(user_input)
            print(f"\033[34massistant:\033[0m {response}\n")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except EOFError:
            break


if __name__ == "__main__":
    main()
