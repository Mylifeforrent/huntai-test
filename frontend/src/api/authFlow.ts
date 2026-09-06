import { toApiError, type ApiError } from "./errors";
import { apiBaseUrl, newIdempotencyKey } from "./apiConfig";
import type { OidcStartResponse, ReauthResponse } from "./types";
import { isOidcAuthFailed, isRequireReauth, isUnauthenticated } from "./errors";

export const OIDC_FAILURE_QUERY_KEY = "oidc";
export const OIDC_FAILURE_QUERY_VALUE = "failed";

let authRedirectInProgress = false;

async function authRequest<T>(options: {
  apiId: string;
  path: string;
  method: "GET" | "POST";
  query?: Record<string, string | undefined>;
  body?: unknown;
}): Promise<T> {
  const { apiId, path, method, query, body } = options;
  const url = new URL(`${apiBaseUrl()}${path}`, window.location.origin);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== "") {
        url.searchParams.set(key, value);
      }
    }
  }
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json; charset=utf-8";
  }
  if (method === "POST") {
    headers["Idempotency-Key"] = newIdempotencyKey();
  }

  let response: Response;
  try {
    response = await fetch(url.pathname + url.search, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "include",
    });
  } catch (cause) {
    throw toApiError({ apiId, path: `${method} ${path}`, cause });
  }

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text) as unknown;
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    throw toApiError({
      apiId,
      path: `${method} ${path}`,
      httpStatus: response.status,
      payload,
    });
  }

  return payload as T;
}

export function isAuthRedirectInProgress(): boolean {
  return authRedirectInProgress;
}

/** Matches backend `validate_return_path` whitelist. */
export function validateReturnPath(returnPath: string): boolean {
  if (!returnPath.startsWith("/")) {
    return false;
  }
  if (returnPath.startsWith("//")) {
    return false;
  }
  if (returnPath.includes("://")) {
    return false;
  }
  return true;
}

export function stripOidcFailureMarker(pathWithSearch: string): string {
  const url = new URL(pathWithSearch, "http://huntai.local");
  url.searchParams.delete(OIDC_FAILURE_QUERY_KEY);
  return `${url.pathname}${url.search}`;
}

export function isOidcFailureRecovery(search: string = window.location.search): boolean {
  return new URLSearchParams(search).get(OIDC_FAILURE_QUERY_KEY) === OIDC_FAILURE_QUERY_VALUE;
}

export function markOidcFailureInUrl(): void {
  const url = new URL(window.location.href);
  if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
    url.pathname = "/";
    url.search = "";
  }
  url.searchParams.set(OIDC_FAILURE_QUERY_KEY, OIDC_FAILURE_QUERY_VALUE);
  window.history.replaceState(null, "", `${url.pathname}${url.search}`);
}

export function clearOidcFailureInUrl(): void {
  if (!isOidcFailureRecovery()) {
    return;
  }
  const next = stripOidcFailureMarker(`${window.location.pathname}${window.location.search}`);
  window.history.replaceState(null, "", next);
}

export function currentReturnPath(): string {
  const pathname = window.location.pathname;
  if (pathname === "/api" || pathname.startsWith("/api/")) {
    return "/";
  }
  return stripOidcFailureMarker(`${pathname}${window.location.search}`);
}

export async function startOidcLogin(
  returnPath?: string,
  options?: { prompt?: "login" },
): Promise<void> {
  if (authRedirectInProgress) {
    return;
  }
  const path = stripOidcFailureMarker(returnPath ?? currentReturnPath());
  if (!validateReturnPath(path)) {
    throw toApiError({
      apiId: "API-001",
      path: "GET /api/v1/auth/oidc/start",
      httpStatus: 400,
      payload: {
        error: {
          code: "HT-VAL-005",
          class: "business",
          subclass: "validation",
          message: "return_path 无效",
          retryable: false,
          trace_id: "client",
        },
      },
    });
  }

  authRedirectInProgress = true;
  try {
    const result = await authRequest<OidcStartResponse>({
      apiId: "API-001",
      path: "/auth/oidc/start",
      method: "GET",
      query: { return_path: path, prompt: options?.prompt },
    });
    window.location.assign(result.authorization_url);
  } catch (error) {
    authRedirectInProgress = false;
    throw error;
  }
}

export async function handleReauth(returnPath?: string): Promise<void> {
  if (authRedirectInProgress) {
    return;
  }
  const path = stripOidcFailureMarker(returnPath ?? currentReturnPath());
  if (!validateReturnPath(path)) {
    throw toApiError({
      apiId: "API-004",
      path: "POST /api/v1/auth/reauth",
      httpStatus: 400,
      payload: {
        error: {
          code: "HT-VAL-005",
          class: "business",
          subclass: "validation",
          message: "return_path 无效",
          retryable: false,
          trace_id: "client",
        },
      },
    });
  }

  authRedirectInProgress = true;
  try {
    const result = await authRequest<ReauthResponse>({
      apiId: "API-004",
      path: "/auth/reauth",
      method: "POST",
      body: { return_path: path },
    });
    if (result.reauth_satisfied === false && result.authorization_url) {
      window.location.assign(result.authorization_url);
      return;
    }
    authRedirectInProgress = false;
  } catch (error) {
    authRedirectInProgress = false;
    throw error;
  }
}

export function handleAuthApiError(error: ApiError): boolean {
  if (isOidcAuthFailed(error)) {
    markOidcFailureInUrl();
    return true;
  }
  if (isUnauthenticated(error)) {
    if (isOidcFailureRecovery()) {
      return true;
    }
    void startOidcLogin(currentReturnPath());
    return true;
  }
  if (isRequireReauth(error)) {
    void handleReauth(currentReturnPath());
    return true;
  }
  return false;
}

export function resetAuthRedirectState(): void {
  authRedirectInProgress = false;
}

