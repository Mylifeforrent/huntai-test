import json
import logging
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

from starlette.requests import Request

TRACE_ID_HEADER = "X-Trace-Id"
TRACE_ID_STATE_KEY = "trace_id"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        trace_id = getattr(record, "trace_id", None)
        if trace_id:
            payload["trace_id"] = trace_id
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())


def get_trace_id(request: Request) -> str:
    trace_id = getattr(request.state, TRACE_ID_STATE_KEY, None)
    if isinstance(trace_id, str):
        return trace_id
    return str(uuid.uuid4())


def log_with_trace(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    trace_id: str,
    **extra: Any,
) -> None:
    record = logger.makeRecord(
        logger.name,
        level,
        "(unknown)",
        0,
        message,
        (),
        None,
    )
    record.trace_id = trace_id
    record.extra_fields = extra
    logger.handle(record)
