from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_trace_id


class AppError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        error_class: str,
        subclass: str,
        message: str,
        retryable: bool,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.error_class = error_class
        self.subclass = subclass
        self.message = message
        self.retryable = retryable
        super().__init__(message)


def error_envelope(
    *,
    code: str,
    error_class: str,
    subclass: str,
    message: str,
    retryable: bool,
    trace_id: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "class": error_class,
        "subclass": subclass,
        "message": message,
        "retryable": retryable,
        "trace_id": trace_id,
    }
    if details is not None:
        error["details"] = details
    return {"error": error}


def unauthenticated(trace_id: str, message: str = "Authentication required") -> AppError:
    return AppError(
        status_code=401,
        code="HT-AUTH-001",
        error_class="permission",
        subclass="unauthenticated",
        message=message,
        retryable=False,
    )


def oidc_auth_failed(trace_id: str) -> AppError:
    return AppError(
        status_code=401,
        code="HT-AUTH-003",
        error_class="permission",
        subclass="unauthenticated",
        message="OIDC authentication failed",
        retryable=False,
    )


def hmac_failed(trace_id: str, message: str = "Webhook signature verification failed") -> AppError:
    return AppError(
        status_code=401,
        code="HT-AUTH-004",
        error_class="permission",
        subclass="unauthenticated",
        message=message,
        retryable=False,
    )


def require_reauth(trace_id: str, message: str = "Step-up authentication required") -> AppError:
    return AppError(
        status_code=401,
        code="HT-AUTH-002",
        error_class="permission",
        subclass="require_reauth",
        message=message,
        retryable=False,
    )


def policy_deny(trace_id: str, message: str = "Policy denied") -> AppError:
    return AppError(
        status_code=403,
        code="HT-POL-001",
        error_class="business",
        subclass="policy_deny",
        message=message,
        retryable=False,
    )


def policy_undeclared(trace_id: str, message: str = "Undeclared side effect level") -> AppError:
    return AppError(
        status_code=403,
        code="HT-POL-002",
        error_class="business",
        subclass="policy_deny",
        message=message,
        retryable=False,
    )


def forbidden(trace_id: str, message: str = "Forbidden") -> AppError:
    return AppError(
        status_code=403,
        code="HT-IAM-001",
        error_class="permission",
        subclass="forbidden",
        message=message,
        retryable=False,
    )


def four_eyes_violation(trace_id: str, message: str = "Four-eyes approval required") -> AppError:
    return AppError(
        status_code=403,
        code="HT-IAM-002",
        error_class="permission",
        subclass="four_eyes",
        message=message,
        retryable=False,
    )


def token_cannot_approve(trace_id: str, message: str = "Token cannot approve") -> AppError:
    return AppError(
        status_code=403,
        code="HT-IAM-003",
        error_class="permission",
        subclass="forbidden",
        message=message,
        retryable=False,
    )


def token_revoked(trace_id: str, message: str = "ApiToken expired or revoked") -> AppError:
    return AppError(
        status_code=401,
        code="HT-IAM-004",
        error_class="permission",
        subclass="forbidden",
        message=message,
        retryable=False,
    )


def token_project_forbidden(trace_id: str, message: str = "Token project not allowed") -> AppError:
    return AppError(
        status_code=403,
        code="HT-IAM-005",
        error_class="permission",
        subclass="forbidden",
        message=message,
        retryable=False,
    )


def state_consumed(trace_id: str, message: str = "Request already consumed") -> AppError:
    return AppError(
        status_code=409,
        code="HT-STATE-002",
        error_class="business",
        subclass="state",
        message=message,
        retryable=False,
    )


def param_hash_invalidated(trace_id: str, message: str = "Parameter hash invalidated") -> AppError:
    return AppError(
        status_code=409,
        code="HT-APPR-001",
        error_class="business",
        subclass="approval",
        message=message,
        retryable=False,
    )


def approval_expired(trace_id: str, message: str = "Approval expired or invalid") -> AppError:
    return AppError(
        status_code=409,
        code="HT-APPR-002",
        error_class="business",
        subclass="approval",
        message=message,
        retryable=False,
    )


def not_found(trace_id: str, message: str = "Resource not found") -> AppError:
    return AppError(
        status_code=404,
        code="HT-RES-001",
        error_class="permission",
        subclass="not_found",
        message=message,
        retryable=False,
    )


def validation_failed(trace_id: str, message: str = "Validation failed") -> AppError:
    return AppError(
        status_code=400,
        code="HT-VAL-001",
        error_class="business",
        subclass="validation",
        message=message,
        retryable=False,
    )


def file_validation_failed(trace_id: str, message: str = "File validation failed") -> AppError:
    return AppError(
        status_code=400,
        code="HT-VAL-003",
        error_class="business",
        subclass="validation",
        message=message,
        retryable=False,
    )


def schema_validation_failed(trace_id: str, message: str = "Schema validation failed") -> AppError:
    return AppError(
        status_code=400,
        code="HT-VAL-004",
        error_class="business",
        subclass="validation",
        message=message,
        retryable=False,
    )


def async_generation_failed(trace_id: str, message: str = "Generation failed") -> AppError:
    return AppError(
        status_code=422,
        code="HT-ASYNC-002",
        error_class="business",
        subclass="async_partial",
        message=message,
        retryable=False,
    )


def precondition_failed(trace_id: str, message: str = "Precondition failed") -> AppError:
    return AppError(
        status_code=409,
        code="HT-STATE-001",
        error_class="business",
        subclass="precondition",
        message=message,
        retryable=False,
    )


def quota_exceeded(trace_id: str, message: str = "Org quota exceeded") -> AppError:
    return AppError(
        status_code=429,
        code="HT-QUOTA-001",
        error_class="business",
        subclass="quota",
        message=message,
        retryable=True,
    )


def version_conflict(trace_id: str, message: str = "Version conflict") -> AppError:
    return AppError(
        status_code=409,
        code="HT-VER-001",
        error_class="business",
        subclass="version_conflict",
        message=message,
        retryable=False,
    )


def open_redirect(trace_id: str) -> AppError:
    return AppError(
        status_code=400,
        code="HT-VAL-005",
        error_class="business",
        subclass="validation",
        message="return_path must be a relative path",
        retryable=False,
    )


def idempotency_conflict(trace_id: str) -> AppError:
    return AppError(
        status_code=409,
        code="HT-IDEM-001",
        error_class="business",
        subclass="idempotency_conflict",
        message="Idempotency key conflict",
        retryable=False,
    )


def internal_error(trace_id: str) -> AppError:
    return AppError(
        status_code=500,
        code="HT-INT-001",
        error_class="business",
        subclass="internal",
        message="An internal error occurred",
        retryable=True,
    )


def app_error_response(request: Request, exc: AppError) -> JSONResponse:
    trace_id = get_trace_id(request)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(
            code=exc.code,
            error_class=exc.error_class,
            subclass=exc.subclass,
            message=exc.message,
            retryable=exc.retryable,
            trace_id=trace_id,
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return app_error_response(request, exc)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        trace_id = get_trace_id(request)
        if exc.status_code == 401:
            return JSONResponse(
                status_code=401,
                content=error_envelope(
                    code="HT-AUTH-001",
                    error_class="permission",
                    subclass="unauthenticated",
                    message="Authentication required",
                    retryable=False,
                    trace_id=trace_id,
                ),
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(
                code="HT-INT-001",
                error_class="business",
                subclass="internal",
                message="An internal error occurred",
                retryable=True,
                trace_id=trace_id,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        trace_id = get_trace_id(request)
        return JSONResponse(
            status_code=400,
            content=error_envelope(
                code="HT-VAL-001",
                error_class="business",
                subclass="validation",
                message="Validation failed",
                retryable=False,
                trace_id=trace_id,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        _ = exc
        trace_id = get_trace_id(request)
        return JSONResponse(
            status_code=500,
            content=error_envelope(
                code="HT-INT-001",
                error_class="business",
                subclass="internal",
                message="An internal error occurred",
                retryable=True,
                trace_id=trace_id,
            ),
        )
