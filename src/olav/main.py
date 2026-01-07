"""OLAV v0.8 - Main Entry Point

This is the main entry point for running OLAV as a CLI application.
"""

from asyncio import run

from langgraph.checkpoint.memory import MemorySaver

from olav.agent import initialize_olav


async def main():
    """Main entry point for OLAV CLI."""
    print("=" * 60)
    print("OLAV v0.8 - Network AI Operations Assistant")
    print("DeepAgents Native Framework")
    print("=" * 60)
    print()

    # Initialize agent
    print("Initializing OLAV...")
    agent = initialize_olav()

    # Create checkpointer for HITL support
    checkpointer = MemorySaver()

    print()
    print("OLAV is ready!")
    print("Type 'quit' or 'exit' to stop")
    print("-" * 60)
    print()

    # Main interaction loop
    thread_id = "main"
    config = {"configurable": {"thread_id": thread_id}}

    while True:
        try:
            # Get user input
            user_input = input("You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit", "q"]:
                print("Goodbye!")
                break

            # Process through agent
            print("\nOLAV: ", end="", flush=True)

            async for chunk in agent.astream(
                {"messages": [{"role": "user", "content": user_input}]},
                config,
            ):
                if "messages" in chunk:
                    for message in chunk["messages"]:
                        if hasattr(message, "content"):
                            print(message.content, end="", flush=True)

            print("\n")

        except KeyboardInterrupt:
            print("\nUse 'quit' to exit.")
        except Exception as e:
            print(f"\nError: {e}\n")


if __name__ == "__main__":
    run(main())
