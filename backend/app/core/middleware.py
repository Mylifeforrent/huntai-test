import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import log_with_trace

_logger = logging.getLogger(__name__)


class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        log_with_trace(
            _logger,
            logging.INFO,
            f"{request.method} {request.url.path} {response.status_code}",
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
        )
        return response
