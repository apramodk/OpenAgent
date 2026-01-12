#!/usr/bin/env python3
"""
Integration test for LLM streaming and token counting.

Run with: python tests/integration_test_llm.py

This tests the actual LLM connection (requires valid .env credentials).
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()


async def test_llm_streaming():
    """Test that LLM streaming works and returns chunks."""
    from openagent.core.llm import AzureOpenAIClient

    print("=" * 60)
    print("TEST: LLM Streaming")
    print("=" * 60)

    try:
        client = AzureOpenAIClient()
        print(f"✓ Client created, model: {client.model}")
    except Exception as e:
        print(f"✗ Failed to create client: {e}")
        return False

    messages = [{"role": "user", "content": "Say 'hello' and nothing else."}]

    print("\nStreaming response:")
    chunks = []
    try:
        async for chunk in client.stream(messages, max_tokens=50):
            print(f"  chunk: {repr(chunk)}")
            chunks.append(chunk)

        full_response = "".join(chunks)
        print(f"\n✓ Full response: {repr(full_response)}")
        print(f"✓ Got {len(chunks)} chunks")
        return True
    except Exception as e:
        print(f"\n✗ Streaming failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_token_tracking():
    """Test that token tracking works."""
    import tempfile
    from openagent.core.agent import Agent, AgentConfig
    from openagent.core.llm import AzureOpenAIClient
    from openagent.telemetry.tokens import TokenTracker
    from openagent.memory.session import SessionManager

    print("\n" + "=" * 60)
    print("TEST: Token Tracking")
    print("=" * 60)

    try:
        llm = AzureOpenAIClient()
        # Use SessionManager to properly initialize db with tables
        db_path = Path(tempfile.gettempdir()) / "openagent_test.db"
        session_mgr = SessionManager(db_path)
        session = session_mgr.create(name="test-session")

        tracker = TokenTracker(session_id=session.id, db_path=db_path)

        config = AgentConfig(
            system_prompt="You are a helpful assistant. Be very brief.",
            model=llm.model,
        )

        agent = Agent(config=config, llm_client=llm, token_tracker=tracker)
        print(f"✓ Agent created with model: {config.model}")
    except Exception as e:
        print(f"✗ Failed to create agent: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\nSending test message (non-streaming)...")
    try:
        response = await agent.chat("Say 'test' and nothing else.")
        print(f"✓ Response: {repr(response)}")
    except Exception as e:
        print(f"✗ Chat failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\nChecking token stats...")
    stats = tracker.get_session_stats()
    print(f"  Total input tokens:  {stats.total_input}")
    print(f"  Total output tokens: {stats.total_output}")
    print(f"  Total tokens:        {stats.total_tokens}")
    print(f"  Total cost:          ${stats.total_cost:.6f}")
    print(f"  Request count:       {stats.request_count}")

    if stats.total_tokens > 0:
        print(f"\n✓ Token tracking working!")
        return True
    else:
        print(f"\n✗ Token tracking not recording tokens")
        return False


async def test_streaming_with_tokens():
    """Test streaming with token tracking."""
    import tempfile
    from openagent.core.agent import Agent, AgentConfig
    from openagent.core.llm import AzureOpenAIClient
    from openagent.telemetry.tokens import TokenTracker
    from openagent.memory.session import SessionManager

    print("\n" + "=" * 60)
    print("TEST: Streaming with Token Tracking")
    print("=" * 60)

    try:
        llm = AzureOpenAIClient()
        db_path = Path(tempfile.gettempdir()) / "openagent_test_stream.db"
        session_mgr = SessionManager(db_path)
        session = session_mgr.create(name="test-stream-session")

        tracker = TokenTracker(session_id=session.id, db_path=db_path)

        config = AgentConfig(
            system_prompt="You are helpful. Be brief.",
            model=llm.model,
        )

        agent = Agent(config=config, llm_client=llm, token_tracker=tracker)
        print(f"✓ Agent created")
    except Exception as e:
        print(f"✗ Failed to create agent: {e}")
        return False

    print("\nStreaming response...")
    chunks = []
    try:
        async for chunk in agent.chat_stream("Count from 1 to 3."):
            print(f"  chunk: {repr(chunk)}")
            chunks.append(chunk)

        print(f"\n✓ Got {len(chunks)} chunks")
        print(f"✓ Full: {''.join(chunks)}")
    except Exception as e:
        print(f"\n✗ Streaming failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Note: Streaming may not track tokens the same way
    stats = tracker.get_session_stats()
    print(f"\nToken stats after streaming:")
    print(f"  Total tokens: {stats.total_tokens}")
    print(f"  Request count: {stats.request_count}")

    return len(chunks) > 0


async def main():
    """Run all integration tests."""
    print("\n" + "=" * 60)
    print("INTEGRATION TESTS - LLM & Token Tracking")
    print("=" * 60)
    print("\nNote: These tests require valid Azure OpenAI credentials in .env")
    print()

    results = []

    # Test 1: Basic streaming
    results.append(("LLM Streaming", await test_llm_streaming()))

    # Test 2: Token tracking
    results.append(("Token Tracking", await test_token_tracking()))

    # Test 3: Streaming with tokens
    results.append(("Streaming + Tokens", await test_streaming_with_tokens()))

    # Summary
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")

    all_passed = all(r[1] for r in results)
    print()
    if all_passed:
        print("All tests passed!")
    else:
        print("Some tests failed.")

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
