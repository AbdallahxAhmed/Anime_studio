"""Desktop backend: ``python -m src.sidecar`` speaks JSON-RPC on stdio."""

from __future__ import annotations

import asyncio
import sys
from typing import Any, MutableMapping

import structlog

from src.sidecar.container import build_services
from src.sidecar.rpc import Channel, RpcServer
from src.sidecar.service import AppService

_FORWARDED_LEVELS = {"info", "warning", "error", "critical"}
_PLAIN_KEYS = ("episode", "font", "error", "subtitle", "problems")


class EventForwarder:
    """structlog processor: progress and readable log lines go to the UI."""

    def __init__(self, channel: Channel) -> None:
        self.channel = channel

    def __call__(
        self, _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        level = str(event_dict.get("level", "")).lower()
        stage = event_dict.get("stage")
        if stage:
            self.channel.notify(
                {
                    "type": "progress",
                    "stage": stage,
                    "current": event_dict.get("progress_current"),
                    "total": event_dict.get("progress_total"),
                    "message": str(event_dict.get("event", "")),
                }
            )
        elif level in _FORWARDED_LEVELS:
            self.channel.notify(
                {
                    "type": "log",
                    "level": level,
                    "message": str(event_dict.get("event", "")),
                    "details": {
                        k: str(event_dict[k]) for k in _PLAIN_KEYS if k in event_dict
                    },
                }
            )
        return event_dict


def configure_logging(channel: Channel) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            EventForwarder(channel),
            structlog.processors.JSONRenderer(),
        ],
        # stdout is the protocol channel: logs must never reach it.
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


async def serve() -> None:
    channel = Channel(sys.stdout)
    configure_logging(channel)
    service = AppService(build_services(), channel.notify)
    server = RpcServer(channel)
    for method, handler in service.handlers().items():
        server.register(method, handler)
    channel.notify({"type": "ready"})
    try:
        await server.serve(sys.stdin)
    finally:
        await service.shutdown()


def main() -> None:
    # Force UTF-8 so Arabic file names survive on Windows consoles.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    asyncio.run(serve())


if __name__ == "__main__":
    main()
