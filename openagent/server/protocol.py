"""JSON-RPC 2.0 protocol types and validation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal
import json


class ErrorCode(Enum):
    """Standard JSON-RPC 2.0 error codes."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # Custom error codes (application-specific)
    SESSION_NOT_FOUND = -32001
    TOOL_NOT_FOUND = -32002
    BUDGET_EXCEEDED = -32003
    CANCELLED = -32004


@dataclass
class RPCError:
    """JSON-RPC error object."""

    code: int
    message: str
    data: Any = None

    def to_dict(self) -> dict:
        d = {"code": self.code, "message": self.message}
        if self.data is not None:
            d["data"] = self.data
        return d

    @classmethod
    def from_code(cls, code: ErrorCode, message: str = "", data: Any = None) -> "RPCError":
        """Create error from ErrorCode enum."""
        default_messages = {
            ErrorCode.PARSE_ERROR: "Parse error",
            ErrorCode.INVALID_REQUEST: "Invalid request",
            ErrorCode.METHOD_NOT_FOUND: "Method not found",
            ErrorCode.INVALID_PARAMS: "Invalid params",
            ErrorCode.INTERNAL_ERROR: "Internal error",
            ErrorCode.SESSION_NOT_FOUND: "Session not found",
            ErrorCode.TOOL_NOT_FOUND: "Tool not found",
            ErrorCode.BUDGET_EXCEEDED: "Token budget exceeded",
            ErrorCode.CANCELLED: "Request cancelled",
        }
        return cls(
            code=code.value,
            message=message or default_messages.get(code, "Unknown error"),
            data=data,
        )


@dataclass
class Request:
    """JSON-RPC 2.0 request."""

    method: str
    params: dict = field(default_factory=dict)
    id: int | str | None = None
    jsonrpc: Literal["2.0"] = "2.0"

    def is_notification(self) -> bool:
        """Check if this is a notification (no response expected)."""
        return self.id is None

    def to_dict(self) -> dict:
        d = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.params:
            d["params"] = self.params
        if self.id is not None:
            d["id"] = self.id
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> "Request":
        return cls(
            method=data.get("method", ""),
            params=data.get("params", {}),
            id=data.get("id"),
            jsonrpc=data.get("jsonrpc", "2.0"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "Request":
        return cls.from_dict(json.loads(json_str))


@dataclass
class Response:
    """JSON-RPC 2.0 response."""

    id: int | str | None
    result: Any = None
    error: RPCError | None = None
    jsonrpc: Literal["2.0"] = "2.0"

    def is_error(self) -> bool:
        return self.error is not None

    def to_dict(self) -> dict:
        d: dict = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error:
            d["error"] = self.error.to_dict()
        else:
            d["result"] = self.result
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def success(cls, id: int | str | None, result: Any) -> "Response":
        return cls(id=id, result=result)

    @classmethod
    def failure(cls, id: int | str | None, error: RPCError) -> "Response":
        return cls(id=id, error=error)

    @classmethod
    def from_dict(cls, data: dict) -> "Response":
        error = None
        if "error" in data:
            err_data = data["error"]
            error = RPCError(
                code=err_data.get("code", -32603),
                message=err_data.get("message", "Unknown error"),
                data=err_data.get("data"),
            )
        return cls(
            id=data.get("id"),
            result=data.get("result"),
            error=error,
            jsonrpc=data.get("jsonrpc", "2.0"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "Response":
        return cls.from_dict(json.loads(json_str))


@dataclass
class Notification:
    """JSON-RPC 2.0 notification (server -> client, no response)."""

    method: str
    params: dict = field(default_factory=dict)
    jsonrpc: Literal["2.0"] = "2.0"

    def to_dict(self) -> dict:
        d: dict = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.params:
            d["params"] = self.params
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> "Notification":
        return cls(
            method=data.get("method", ""),
            params=data.get("params", {}),
            jsonrpc=data.get("jsonrpc", "2.0"),
        )


# ============================================================================
# Protocol Method Definitions
# ============================================================================

class Methods:
    """Available JSON-RPC methods."""

    # Chat methods
    CHAT_SEND = "chat.send"
    CHAT_CANCEL = "chat.cancel"

    # Session methods
    SESSION_CREATE = "session.create"
    SESSION_LOAD = "session.load"
    SESSION_LIST = "session.list"
    SESSION_DELETE = "session.delete"

    # Token methods
    TOKENS_GET = "tokens.get"
    TOKENS_SET_BUDGET = "tokens.set_budget"

    # Tool methods
    TOOLS_LIST = "tools.list"
    TOOLS_CALL = "tools.call"

    # RAG methods
    RAG_SEARCH = "rag.search"
    RAG_INGEST = "rag.ingest"


class Notifications:
    """Server -> Client notification methods."""

    # Streaming response
    RESPONSE_CHUNK = "response.chunk"
    RESPONSE_DONE = "response.done"

    # Token updates
    TOKEN_UPDATE = "token.update"

    # Tool execution
    TOOL_CALL = "tool.call"
    TOOL_RESULT = "tool.result"

    # Status
    STATUS = "status"
    ERROR = "error"


# ============================================================================
# Parameter/Result Schemas (for documentation and validation)
# ============================================================================

SCHEMAS: dict[str, dict] = {
    # chat.send
    Methods.CHAT_SEND: {
        "params": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "User message"},
                "stream": {"type": "boolean", "default": True},
            },
            "required": ["message"],
        },
        "result": {
            "type": "object",
            "properties": {
                "response": {"type": "string"},
                "tokens": {"$ref": "#/definitions/TokenStats"},
            },
        },
    },
    # session.create
    Methods.SESSION_CREATE: {
        "params": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "codebase_path": {"type": "string"},
            },
        },
        "result": {"$ref": "#/definitions/Session"},
    },
    # session.load
    Methods.SESSION_LOAD: {
        "params": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
            },
            "required": ["id"],
        },
        "result": {"$ref": "#/definitions/Session"},
    },
    # session.list
    Methods.SESSION_LIST: {
        "params": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
            },
        },
        "result": {
            "type": "object",
            "properties": {
                "sessions": {"type": "array", "items": {"$ref": "#/definitions/Session"}},
            },
        },
    },
    # tokens.get
    Methods.TOKENS_GET: {
        "params": {"type": "object"},
        "result": {"$ref": "#/definitions/TokenStats"},
    },
    # Shared definitions
    "definitions": {
        "Session": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "codebase_path": {"type": "string", "nullable": True},
                "created_at": {"type": "string", "format": "date-time"},
                "last_accessed": {"type": "string", "format": "date-time"},
                "metadata": {"type": "object"},
            },
        },
        "TokenStats": {
            "type": "object",
            "properties": {
                "total_input": {"type": "integer"},
                "total_output": {"type": "integer"},
                "total_tokens": {"type": "integer"},
                "total_cost": {"type": "number"},
                "request_count": {"type": "integer"},
                "budget": {"type": "integer", "nullable": True},
                "budget_remaining": {"type": "integer", "nullable": True},
                "budget_percentage": {"type": "number", "nullable": True},
            },
        },
    },
}


def validate_request(request: Request) -> RPCError | None:
    """
    Validate a request.

    Returns None if valid, RPCError if invalid.
    """
    if request.jsonrpc != "2.0":
        return RPCError.from_code(
            ErrorCode.INVALID_REQUEST,
            f"Invalid jsonrpc version: {request.jsonrpc}",
        )

    if not request.method:
        return RPCError.from_code(
            ErrorCode.INVALID_REQUEST,
            "Missing method",
        )

    # Check if method exists
    all_methods = [
        getattr(Methods, attr)
        for attr in dir(Methods)
        if not attr.startswith("_")
    ]
    if request.method not in all_methods:
        return RPCError.from_code(
            ErrorCode.METHOD_NOT_FOUND,
            f"Unknown method: {request.method}",
        )

    return None
