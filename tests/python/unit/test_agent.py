import pytest
from unittest.mock import MagicMock, AsyncMock
from openagent.core.agent import Agent, AgentConfig, Message
from openagent.core.llm import LLMResponse

def test_agent_initialization(mock_llm_client):
    """Test that agent initializes with correct config and client."""
    config = AgentConfig(model="test-model", system_prompt="Test system prompt")
    agent = Agent(config=config, llm_client=mock_llm_client)
    
    assert agent.config.model == "test-model"
    assert agent.llm == mock_llm_client
    assert not agent.is_persistent
    
    # Check system prompt is added
    assert len(agent._messages) == 1
    assert agent._messages[0].role == "system"
    assert agent._messages[0].content == "Test system prompt"

def test_agent_initialization_defaults(mock_llm_client):
    """Test default initialization."""
    # We must pass the mock client to avoid AzureOpenAIClient default
    agent = Agent(llm_client=mock_llm_client)
    
    assert agent.config.model == "gpt-4.1"  # Default from AgentConfig
    assert len(agent._messages) == 0  # No default system prompt in AgentConfig

def test_chat_sync(mock_llm_client):
    """Test synchronous chat."""
    agent = Agent(llm_client=mock_llm_client)
    
    user_msg = "Hello"
    response = agent.chat_sync(user_msg)
    
    assert response == "Mock response"
    
    # Check messages are recorded
    assert len(agent._messages) == 2
    assert agent._messages[0].role == "user"
    assert agent._messages[0].content == user_msg
    assert agent._messages[1].role == "assistant"
    assert agent._messages[1].content == "Mock response"
    
    # Verify LLM was called with correct context
    mock_llm_client.complete_sync_mock.assert_called_once()
    call_args = mock_llm_client.complete_sync_mock.call_args
    assert call_args[0][0][-1]['content'] == user_msg

@pytest.mark.asyncio
async def test_chat_async(mock_llm_client):
    """Test asynchronous chat."""
    agent = Agent(llm_client=mock_llm_client)
    
    user_msg = "Hello Async"
    response = await agent.chat(user_msg)
    
    assert response == "Mock response"
    
    assert len(agent._messages) == 2
    assert agent._messages[0].content == user_msg
    assert agent._messages[1].content == "Mock response"
    
    mock_llm_client.complete_mock.assert_called_once()

@pytest.mark.asyncio
async def test_chat_stream(mock_llm_client):
    """Test streaming chat."""
    agent = Agent(llm_client=mock_llm_client)
    
    chunks = []
    async for chunk in agent.chat_stream("Stream me"):
        chunks.append(chunk)
    
    full_response = "".join(chunks)
    assert "Mock" in full_response
    assert "response" in full_response
    
    # Verify the full message was recorded
    assert len(agent._messages) == 2
    assert agent._messages[1].role == "assistant"
    assert agent._messages[1].content.strip() == full_response.strip()

def test_context_building_in_memory(mock_llm_client):
    """Test context construction in in-memory mode."""
    config = AgentConfig(system_prompt="System")
    agent = Agent(config=config, llm_client=mock_llm_client)
    
    # Add some history
    agent._messages.append(Message(role="user", content="Old user"))
    agent._messages.append(Message(role="assistant", content="Old assistant"))
    
    # Test with RAG context
    rag_context = "Some code context"
    context = agent._get_context("New user", rag_context=rag_context)
    
    # Expected: System, User (Old), Assistant (Old), System (RAG), User (New)
    assert len(context) == 5
    assert context[0]['role'] == "system"
    assert context[0]['content'] == "System"
    
    assert context[3]['role'] == "system"
    assert "Some code context" in context[3]['content']
    
    assert context[4]['role'] == "user"
    assert context[4]['content'] == "New user"

def test_clear_history(mock_llm_client):
    """Test clearing history."""
    config = AgentConfig(system_prompt="System")
    agent = Agent(config=config, llm_client=mock_llm_client)
    
    agent.chat_sync("Message 1")
    assert len(agent._messages) == 3 # System + User + Assistant
    
    agent.clear_history(keep_system=True)
    assert len(agent._messages) == 1
    assert agent._messages[0].role == "system"
    
    agent.chat_sync("Message 2")
    agent.clear_history(keep_system=False)
    assert len(agent._messages) == 0
