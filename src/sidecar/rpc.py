"""Newline-delimited JSON-RPC 2.0 over stdin/stdout.

stdout carries protocol messages only; all logging goes to stderr.  Requests
are handled concurrently; notifications (method ``event``) stream progress.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import traceback
from typing import Any, Awaitable, Callable, TextIO

Handler = Callable[[dict[str, Any]], Awaitable[Any]]

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
APP_ERROR = -32000


class RpcError(Exception):
    """An error the client should see, with a JSON-RPC code."""

    def __init__(self, message: str, code: int = APP_ERROR) -> None:
        super().__init__(message)
        self.code = code


class Channel:
    """Thread-safe writer of protocol messages."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._lock = threading.Lock()

    def send(self, message: dict[str, Any]) -> None:
        line = json.dumps(message, ensure_ascii=False, default=str)
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()

    def notify(self, params: dict[str, Any]) -> None:
        self.send({"jsonrpc": "2.0", "method": "event", "params": params})


class RpcServer:
    def __init__(self, channel: Channel) -> None:
        self.channel = channel
        self._handlers: dict[str, Handler] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def register(self, method: str, handler: Handler) -> None:
        self._handlers[method] = handler

    async def handle_line(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            message = json.loads(line)
        except json.JSONDecodeError as error:
            self._error(None, PARSE_ERROR, f"invalid JSON: {error}")
            return
        if not isinstance(message, dict) or not isinstance(message.get("method"), str):
            self._error(None, INVALID_REQUEST, "expected a JSON-RPC request object")
            return
        task = asyncio.create_task(self._dispatch(message))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _dispatch(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        method = message["method"]
        params = message.get("params") or {}
        handler = self._handlers.get(method)
        if handler is None:
            self._error(request_id, METHOD_NOT_FOUND, f"unknown method {method}")
            return
        if not isinstance(params, dict):
            self._error(request_id, INVALID_PARAMS, "params must be an object")
            return
        try:
            result = await handler(params)
        except RpcError as error:
            self._error(request_id, error.code, str(error))
            return
        except Exception as error:  # report, never crash the backend
            traceback.print_exc(file=sys.stderr)
            self._error(request_id, APP_ERROR, f"{type(error).__name__}: {error}")
            return
        if request_id is not None:
            self.channel.send({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _error(self, request_id: Any, code: int, message: str) -> None:
        self.channel.send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": code, "message": message},
            }
        )

    async def serve(self, stream: TextIO) -> None:
        """Read requests until EOF.  A reader thread keeps this portable."""
        loop = asyncio.get_running_loop()
        lines: asyncio.Queue[str | None] = asyncio.Queue()

        def _reader() -> None:
            for raw in stream:
                loop.call_soon_threadsafe(lines.put_nowait, raw)
            loop.call_soon_threadsafe(lines.put_nowait, None)

        threading.Thread(target=_reader, name="rpc-stdin", daemon=True).start()
        while True:
            line = await lines.get()
            if line is None:
                break
            await self.handle_line(line)
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
