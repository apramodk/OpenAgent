"""Tests for JSON-RPC protocol types.

## Test Classification

| Category | Tests | Description |
|----------|-------|-------------|
| Serialization | 8 | Request/Response/Notification to_dict, to_json |
| Deserialization | 6 | from_dict, from_json parsing |
| Error Handling | 5 | RPCError creation, error codes |
| Validation | 4 | Request validation, method checks |
| Edge Cases | 3 | Notifications, empty params, null IDs |
"""

import pytest
import json

from openagent.server.protocol import (
    Request,
    Response,
    Notification,
    RPCError,
    ErrorCode,
    Methods,
    Notifications,
    validate_request,
)


class TestRequest:
    """Tests for Request dataclass."""

    def test_to_dict_minimal(self):
        """Test minimal request serialization."""
        req = Request(method="test.method", id=1)
        d = req.to_dict()

        assert d == {
            "jsonrpc": "2.0",
            "method": "test.method",
            "id": 1,
        }

    def test_to_dict_with_params(self):
        """Test request with params serialization."""
        req = Request(
            method="chat.send",
            params={"message": "Hello"},
            id=1,
        )
        d = req.to_dict()

        assert d["params"] == {"message": "Hello"}

    def test_to_json(self):
        """Test JSON string output."""
        req = Request(method="test", id=1)
        j = req.to_json()

        parsed = json.loads(j)
        assert parsed["method"] == "test"

    def test_from_dict(self):
        """Test request deserialization."""
        data = {
            "jsonrpc": "2.0",
            "method": "session.create",
            "params": {"name": "Test"},
            "id": 42,
        }
        req = Request.from_dict(data)

        assert req.method == "session.create"
        assert req.params == {"name": "Test"}
        assert req.id == 42

    def test_from_json(self):
        """Test request from JSON string."""
        json_str = '{"jsonrpc": "2.0", "method": "test", "id": 1}'
        req = Request.from_json(json_str)

        assert req.method == "test"
        assert req.id == 1

    def test_is_notification_true(self):
        """Test notification detection (no id)."""
        req = Request(method="status", id=None)
        assert req.is_notification() is True

    def test_is_notification_false(self):
        """Test non-notification (has id)."""
        req = Request(method="test", id=1)
        assert req.is_notification() is False

    def test_string_id(self):
        """Test request with string ID."""
        req = Request(method="test", id="abc-123")
        d = req.to_dict()

        assert d["id"] == "abc-123"

    def test_empty_params_not_included(self):
        """Test that empty params are not included in dict."""
        req = Request(method="test", params={}, id=1)
        d = req.to_dict()

        assert "params" not in d


class TestResponse:
    """Tests for Response dataclass."""

    def test_success_response(self):
        """Test successful response creation."""
        resp = Response.success(id=1, result={"data": "value"})

        assert resp.id == 1
        assert resp.result == {"data": "value"}
        assert resp.error is None
        assert resp.is_error() is False

    def test_failure_response(self):
        """Test error response creation."""
        error = RPCError(code=-32600, message="Invalid request")
        resp = Response.failure(id=1, error=error)

        assert resp.id == 1
        assert resp.error is not None
        assert resp.is_error() is True

    def test_to_dict_success(self):
        """Test success response serialization."""
        resp = Response.success(id=1, result="ok")
        d = resp.to_dict()

        assert d == {
            "jsonrpc": "2.0",
            "id": 1,
            "result": "ok",
        }
        assert "error" not in d

    def test_to_dict_error(self):
        """Test error response serialization."""
        resp = Response.failure(
            id=1,
            error=RPCError(code=-32601, message="Method not found"),
        )
        d = resp.to_dict()

        assert d["error"]["code"] == -32601
        assert d["error"]["message"] == "Method not found"
        assert "result" not in d

    def test_to_json(self):
        """Test JSON output."""
        resp = Response.success(id=1, result="test")
        j = resp.to_json()

        parsed = json.loads(j)
        assert parsed["result"] == "test"

    def test_from_dict_success(self):
        """Test success response deserialization."""
        data = {"jsonrpc": "2.0", "id": 1, "result": {"key": "value"}}
        resp = Response.from_dict(data)

        assert resp.result == {"key": "value"}
        assert resp.error is None

    def test_from_dict_error(self):
        """Test error response deserialization."""
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32600, "message": "Bad request"},
        }
        resp = Response.from_dict(data)

        assert resp.error is not None
        assert resp.error.code == -32600
        assert resp.error.message == "Bad request"

    def test_null_id(self):
        """Test response with null ID (for notification errors)."""
        resp = Response.success(id=None, result="ok")
        d = resp.to_dict()

        assert d["id"] is None


class TestNotification:
    """Tests for Notification dataclass."""

    def test_to_dict(self):
        """Test notification serialization."""
        notif = Notification(
            method="token.update",
            params={"total": 1000},
        )
        d = notif.to_dict()

        assert d == {
            "jsonrpc": "2.0",
            "method": "token.update",
            "params": {"total": 1000},
        }
        assert "id" not in d

    def test_to_json(self):
        """Test JSON output."""
        notif = Notification(method="status", params={"ready": True})
        j = notif.to_json()

        parsed = json.loads(j)
        assert parsed["method"] == "status"
        assert "id" not in parsed

    def test_from_dict(self):
        """Test notification deserialization."""
        data = {
            "jsonrpc": "2.0",
            "method": "response.chunk",
            "params": {"chunk": "Hello"},
        }
        notif = Notification.from_dict(data)

        assert notif.method == "response.chunk"
        assert notif.params == {"chunk": "Hello"}

    def test_empty_params(self):
        """Test notification with empty params."""
        notif = Notification(method="status")
        d = notif.to_dict()

        assert "params" not in d


class TestRPCError:
    """Tests for RPCError dataclass."""

    def test_to_dict(self):
        """Test error serialization."""
        err = RPCError(code=-32600, message="Invalid request")
        d = err.to_dict()

        assert d == {"code": -32600, "message": "Invalid request"}

    def test_to_dict_with_data(self):
        """Test error with additional data."""
        err = RPCError(
            code=-32602,
            message="Invalid params",
            data={"missing": ["name"]},
        )
        d = err.to_dict()

        assert d["data"] == {"missing": ["name"]}

    def test_from_code_with_default_message(self):
        """Test error creation from code with default message."""
        err = RPCError.from_code(ErrorCode.METHOD_NOT_FOUND)

        assert err.code == -32601
        assert err.message == "Method not found"

    def test_from_code_with_custom_message(self):
        """Test error creation from code with custom message."""
        err = RPCError.from_code(
            ErrorCode.METHOD_NOT_FOUND,
            message="Unknown method: foo.bar",
        )

        assert err.code == -32601
        assert err.message == "Unknown method: foo.bar"

    def test_from_code_with_data(self):
        """Test error creation with additional data."""
        err = RPCError.from_code(
            ErrorCode.INVALID_PARAMS,
            data={"field": "message"},
        )

        assert err.data == {"field": "message"}


class TestErrorCode:
    """Tests for ErrorCode enum."""

    def test_standard_codes(self):
        """Test standard JSON-RPC error codes."""
        assert ErrorCode.PARSE_ERROR.value == -32700
        assert ErrorCode.INVALID_REQUEST.value == -32600
        assert ErrorCode.METHOD_NOT_FOUND.value == -32601
        assert ErrorCode.INVALID_PARAMS.value == -32602
        assert ErrorCode.INTERNAL_ERROR.value == -32603

    def test_custom_codes(self):
        """Test custom application error codes."""
        assert ErrorCode.SESSION_NOT_FOUND.value == -32001
        assert ErrorCode.TOOL_NOT_FOUND.value == -32002
        assert ErrorCode.BUDGET_EXCEEDED.value == -32003
        assert ErrorCode.CANCELLED.value == -32004


class TestMethods:
    """Tests for Methods constants."""

    def test_chat_methods(self):
        """Test chat method names."""
        assert Methods.CHAT_SEND == "chat.send"
        assert Methods.CHAT_CANCEL == "chat.cancel"

    def test_session_methods(self):
        """Test session method names."""
        assert Methods.SESSION_CREATE == "session.create"
        assert Methods.SESSION_LOAD == "session.load"
        assert Methods.SESSION_LIST == "session.list"
        assert Methods.SESSION_DELETE == "session.delete"

    def test_token_methods(self):
        """Test token method names."""
        assert Methods.TOKENS_GET == "tokens.get"
        assert Methods.TOKENS_SET_BUDGET == "tokens.set_budget"


class TestNotifications:
    """Tests for Notifications constants."""

    def test_response_notifications(self):
        """Test response notification names."""
        assert Notifications.RESPONSE_CHUNK == "response.chunk"
        assert Notifications.RESPONSE_DONE == "response.done"

    def test_token_notifications(self):
        """Test token notification names."""
        assert Notifications.TOKEN_UPDATE == "token.update"

    def test_tool_notifications(self):
        """Test tool notification names."""
        assert Notifications.TOOL_CALL == "tool.call"
        assert Notifications.TOOL_RESULT == "tool.result"


class TestValidateRequest:
    """Tests for request validation."""

    def test_valid_request(self):
        """Test validation passes for valid request."""
        req = Request(method=Methods.CHAT_SEND, id=1)
        error = validate_request(req)

        assert error is None

    def test_invalid_jsonrpc_version(self):
        """Test validation fails for wrong version."""
        req = Request(method="test", id=1)
        req.jsonrpc = "1.0"  # type: ignore
        error = validate_request(req)

        assert error is not None
        assert error.code == ErrorCode.INVALID_REQUEST.value

    def test_missing_method(self):
        """Test validation fails for missing method."""
        req = Request(method="", id=1)
        error = validate_request(req)

        assert error is not None
        assert error.code == ErrorCode.INVALID_REQUEST.value

    def test_unknown_method(self):
        """Test validation fails for unknown method."""
        req = Request(method="unknown.method", id=1)
        error = validate_request(req)

        assert error is not None
        assert error.code == ErrorCode.METHOD_NOT_FOUND.value
