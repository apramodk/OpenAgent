"""Tests for JSON-RPC server implementation.

## Test Classification

| Category | Tests | Description |
|----------|-------|-------------|
| Handler Registration | 3 | register, register_all, handler lookup |
| Request Handling | 4 | Success, error, notification, unknown method |
| Response Writing | 2 | Sync write, error formatting |
| Server Lifecycle | 2 | Start, stop |
"""

import pytest
import json
import asyncio

from openagent.server.jsonrpc import JSONRPCServer
from openagent.server.protocol import Request, Response, ErrorCode


class TestJSONRPCServer:
    """Tests for JSONRPCServer class."""

    @pytest.fixture
    def server(self) -> JSONRPCServer:
        """Create a fresh server instance."""
        return JSONRPCServer()

    def test_register_handler(self, server: JSONRPCServer):
        """Test registering a single handler."""
        async def my_handler(params: dict) -> str:
            return "ok"

        server.register("test.method", my_handler)

        assert "test.method" in server._handlers
        assert server._handlers["test.method"] is my_handler

    def test_register_all(self, server: JSONRPCServer):
        """Test registering multiple handlers at once."""
        async def handler1(params: dict) -> str:
            return "one"

        async def handler2(params: dict) -> str:
            return "two"

        server.register_all({
            "method.one": handler1,
            "method.two": handler2,
        })

        assert "method.one" in server._handlers
        assert "method.two" in server._handlers

    def test_register_overwrites(self, server: JSONRPCServer):
        """Test that registering same method overwrites."""
        async def handler1(params: dict) -> str:
            return "first"

        async def handler2(params: dict) -> str:
            return "second"

        server.register("test", handler1)
        server.register("test", handler2)

        assert server._handlers["test"] is handler2

    @pytest.mark.asyncio
    async def test_handle_success(self, server: JSONRPCServer):
        """Test successful request handling."""
        async def echo(params: dict) -> dict:
            return {"echo": params.get("message", "")}

        server.register("echo", echo)

        request_data = {
            "jsonrpc": "2.0",
            "method": "echo",
            "params": {"message": "hello"},
            "id": 1,
        }

        response = await server._handle(request_data)

        assert response is not None
        assert response["result"] == {"echo": "hello"}
        assert response["id"] == 1

    @pytest.mark.asyncio
    async def test_handle_error(self, server: JSONRPCServer):
        """Test error handling in request."""
        async def failing(params: dict) -> None:
            raise ValueError("Something went wrong")

        server.register("fail", failing)

        request_data = {
            "jsonrpc": "2.0",
            "method": "fail",
            "id": 1,
        }

        response = await server._handle(request_data)

        assert response is not None
        assert "error" in response
        assert response["error"]["code"] == -32603
        assert "Something went wrong" in response["error"]["message"]

    @pytest.mark.asyncio
    async def test_handle_notification(self, server: JSONRPCServer):
        """Test notification handling (no response)."""
        called = {"count": 0}

        async def notify_handler(params: dict) -> None:
            called["count"] += 1

        server.register("notify", notify_handler)

        request_data = {
            "jsonrpc": "2.0",
            "method": "notify",
            "params": {},
            # No id = notification
        }

        response = await server._handle(request_data)

        assert response is None  # No response for notifications
        assert called["count"] == 1

    @pytest.mark.asyncio
    async def test_handle_unknown_method(self, server: JSONRPCServer):
        """Test handling of unknown method."""
        request_data = {
            "jsonrpc": "2.0",
            "method": "unknown.method",
            "id": 1,
        }

        response = await server._handle(request_data)

        assert response is not None
        assert response["error"]["code"] == ErrorCode.METHOD_NOT_FOUND.value

    @pytest.mark.asyncio
    async def test_handle_unknown_method_notification(self, server: JSONRPCServer):
        """Test unknown method as notification returns nothing."""
        request_data = {
            "jsonrpc": "2.0",
            "method": "unknown.method",
            # No id = notification
        }

        response = await server._handle(request_data)

        # Notifications don't get error responses
        assert response is None

    def test_error_response_format(self, server: JSONRPCServer):
        """Test error response formatting."""
        error_resp = server._error(-32600, "Invalid request", 42)

        assert error_resp["jsonrpc"] == "2.0"
        assert error_resp["id"] == 42
        assert error_resp["error"]["code"] == -32600
        assert error_resp["error"]["message"] == "Invalid request"

    def test_stop(self, server: JSONRPCServer):
        """Test stopping the server."""
        server._running = True
        server.stop()

        assert server._running is False


class TestJSONRPCIntegration:
    """Integration tests for JSON-RPC request/response cycles."""

    @pytest.fixture
    def server(self) -> JSONRPCServer:
        """Create server with test handlers."""
        server = JSONRPCServer()

        async def add(params: dict) -> int:
            return params.get("a", 0) + params.get("b", 0)

        async def greet(params: dict) -> str:
            name = params.get("name", "World")
            return f"Hello, {name}!"

        async def get_data(params: dict) -> dict:
            return {
                "items": [1, 2, 3],
                "count": 3,
            }

        server.register_all({
            "math.add": add,
            "greet": greet,
            "data.get": get_data,
        })

        return server

    @pytest.mark.asyncio
    async def test_math_operation(self, server: JSONRPCServer):
        """Test math operation request."""
        response = await server._handle({
            "jsonrpc": "2.0",
            "method": "math.add",
            "params": {"a": 5, "b": 3},
            "id": 1,
        })

        assert response["result"] == 8

    @pytest.mark.asyncio
    async def test_string_operation(self, server: JSONRPCServer):
        """Test string operation request."""
        response = await server._handle({
            "jsonrpc": "2.0",
            "method": "greet",
            "params": {"name": "Alice"},
            "id": "req-1",
        })

        assert response["result"] == "Hello, Alice!"
        assert response["id"] == "req-1"

    @pytest.mark.asyncio
    async def test_complex_response(self, server: JSONRPCServer):
        """Test complex object response."""
        response = await server._handle({
            "jsonrpc": "2.0",
            "method": "data.get",
            "params": {},
            "id": 100,
        })

        assert response["result"]["items"] == [1, 2, 3]
        assert response["result"]["count"] == 3

    @pytest.mark.asyncio
    async def test_default_params(self, server: JSONRPCServer):
        """Test handler with default params."""
        response = await server._handle({
            "jsonrpc": "2.0",
            "method": "greet",
            "id": 1,
            # No params - should use default
        })

        assert response["result"] == "Hello, World!"
