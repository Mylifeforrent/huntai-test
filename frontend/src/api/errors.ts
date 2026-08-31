import type { ApiErrorBody, ErrorClass, ErrorEnvelope } from "./types";

export type ApiFailureKind = "undeveloped" | "network" | "permission" | "business" | "not_found";

export class ApiError extends Error {
  readonly kind: ApiFailureKind;
  readonly httpStatus: number | null;
  readonly apiId: string;
  readonly path: string;
  readonly body: ApiErrorBody | null;
  readonly retryable: boolean;

  constructor(init: {
    kind: ApiFailureKind;
    message: string;
    httpStatus?: number | null;
    apiId: string;
    path: string;
    body?: ApiErrorBody | null;
    retryable?: boolean;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.kind = init.kind;
    this.httpStatus = init.httpStatus ?? null;
    this.apiId = init.apiId;
    this.path = init.path;
    this.body = init.body ?? null;
    this.retryable = init.retryable ?? false;
  }
}

export function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== "object" || value === null || !("error" in value)) {
    return false;
  }
  const error = (value as ErrorEnvelope).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof error.code === "string" &&
    typeof error.class === "string" &&
    typeof error.message === "string"
  );
}

export function classifyHttpFailure(httpStatus: number, body: ApiErrorBody | null): ApiFailureKind {
  if (httpStatus === 501) {
    return "undeveloped";
  }
  if (httpStatus === 404 && !body) {
    return "undeveloped";
  }
  if (httpStatus === 404) {
    return "not_found";
  }
  if (!body) {
    if (httpStatus >= 500) {
      return "network";
    }
    return "undeveloped";
  }
  const cls: ErrorClass = body.class;
  if (cls === "permission") {
    return httpStatus === 404 ? "not_found" : "permission";
  }
  if (cls === "network") {
    return "network";
  }
  return "business";
}

export function toApiError(params: {
  apiId: string;
  path: string;
  httpStatus?: number | null;
  payload?: unknown;
  cause?: unknown;
}): ApiError {
  const { apiId, path, httpStatus = null, payload, cause } = params;

  if (cause instanceof TypeError || (cause instanceof Error && /fetch|network|ECONNREFUSED/i.test(cause.message))) {
    return new ApiError({
      kind: "undeveloped",
      message: "后端未开发或不可达",
      httpStatus,
      apiId,
      path,
      retryable: true,
    });
  }

  if (isErrorEnvelope(payload)) {
    const kind = classifyHttpFailure(httpStatus ?? 0, payload.error);
    return new ApiError({
      kind,
      message: payload.error.message,
      httpStatus,
      apiId,
      path,
      body: payload.error,
      retryable: payload.error.retryable,
    });
  }

  if (httpStatus === null) {
    return new ApiError({
      kind: "undeveloped",
      message: "后端未开发或不可达",
      apiId,
      path,
      retryable: true,
    });
  }

  const kind = classifyHttpFailure(httpStatus, null);
  return new ApiError({
    kind,
    message: kind === "undeveloped" ? "后端未开发" : `请求失败 (${httpStatus})`,
    httpStatus,
    apiId,
    path,
    retryable: httpStatus >= 500,
  });
}

export function isUndeveloped(error: unknown): boolean {
  return error instanceof ApiError && error.kind === "undeveloped";
}
