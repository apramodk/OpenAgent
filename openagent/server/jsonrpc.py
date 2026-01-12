"""JSON-RPC 2.0 server over stdio."""

import asyncio
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Literal


Handler = Callable[[dict], Awaitable[Any]]


@dataclass
class Request:
    """JSON-RPC request."""

    method: str
    params: dict = field(default_factory=dict)
    id: int | str | None = None
    jsonrpc: Literal["2.0"] = "2.0"

    @classmethod
    def from_dict(cls, data: dict) -> "Request":
        return cls(
            method=data.get("method", ""),
            params=data.get("params", {}),
            id=data.get("id"),
            jsonrpc=data.get("jsonrpc", "2.0"),
        )


@dataclass
class Response:
    """JSON-RPC response."""

    result: Any = None
    error: dict | None = None
    id: int | str | None = None
    jsonrpc: Literal["2.0"] = "2.0"

    def to_dict(self) -> dict:
        d = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error:
            d["error"] = self.error
        else:
            d["result"] = self.result
        return d


@dataclass
class Notification:
    """JSON-RPC notification (no response expected)."""

    method: str
    params: dict = field(default_factory=dict)
    jsonrpc: Literal["2.0"] = "2.0"

    def to_dict(self) -> dict:
        return {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
            "params": self.params,
        }


class JSONRPCServer:
    """JSON-RPC 2.0 server over stdio."""

    def __init__(self):
        self._handlers: dict[str, Handler] = {}
        self._running = False
        self._writer: asyncio.StreamWriter | None = None

    def register(self, method: str, handler: Handler) -> None:
        """Register a method handler."""
        self._handlers[method] = handler

    def register_all(self, handlers: dict[str, Handler]) -> None:
        """Register multiple handlers at once."""
        self._handlers.update(handlers)

    async def run(self) -> None:
        """Main server loop - read from stdin, write to stdout."""
        self._running = True

        # Set up async stdin reader
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        # Set up async stdout writer
        writer_transport, writer_protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        self._writer = asyncio.StreamWriter(
            writer_transport, writer_protocol, reader, loop
        )

        while self._running:
            try:
                line = await reader.readline()
                if not line:
                    break

                request_data = json.loads(line.decode().strip())
                response = await self._handle(request_data)

                if response:  # Notifications don't get responses
                    await self._write(response)

            except json.JSONDecodeError as e:
                await self._write(self._error(-32700, f"Parse error: {e}", None))
            except Exception as e:
                await self._write(self._error(-32603, f"Internal error: {e}", None))

    async def _handle(self, data: dict) -> dict | None:
        """Handle a single request."""
        request = Request.from_dict(data)

        handler = self._handlers.get(request.method)
        if not handler:
            if request.id is not None:
                return self._error(-32601, f"Method not found: {request.method}", request.id)
            return None

        try:
            result = await handler(request.params)
            if request.id is None:  # Notification
                return None
            return Response(result=result, id=request.id).to_dict()
        except Exception as e:
            if request.id is not None:
                return self._error(-32603, str(e), request.id)
            return None

    async def notify(self, method: str, params: dict) -> None:
        """Send a notification to the client."""
        notification = Notification(method=method, params=params)
        await self._write(notification.to_dict())

    def notify_sync(self, method: str, params: dict) -> None:
        """Synchronous notification (for use outside async context)."""
        notification = Notification(method=method, params=params)
        sys.stdout.write(json.dumps(notification.to_dict()) + "\n")
        sys.stdout.flush()

    async def _write(self, data: dict) -> None:
        """Write JSON line to stdout."""
        if self._writer:
            self._writer.write((json.dumps(data) + "\n").encode())
            await self._writer.drain()
        else:
            sys.stdout.write(json.dumps(data) + "\n")
            sys.stdout.flush()

    def _error(self, code: int, message: str, request_id: Any) -> dict:
        """Create an error response."""
        return Response(
            error={"code": code, "message": message},
            id=request_id,
        ).to_dict()

    def stop(self) -> None:
        """Stop the server."""
        self._running = False
