import { toApiError } from "./errors";
import { handleAuthApiError } from "./authFlow";
import { apiBaseUrl, newIdempotencyKey } from "./apiConfig";

export { apiBaseUrl, newIdempotencyKey } from "./apiConfig";

interface RequestOptions {
  apiId: string;
  path: string;
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  query?: Record<string, string | number | boolean | undefined | null>;
  body?: unknown;
  idempotencyKey?: string;
  signal?: AbortSignal;
  skipAuthIntercept?: boolean;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const base = path.startsWith("http") ? path : `${apiBaseUrl()}${path.startsWith("/api/") ? path.slice("/api/v1".length) : path}`;
  const url = new URL(base, window.location.origin);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.pathname + url.search;
}

export async function apiRequest<T>(options: RequestOptions): Promise<T> {
  const { apiId, path, method = "GET", query, body, idempotencyKey, signal, skipAuthIntercept } = options;
  const url = buildUrl(path, query);
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json; charset=utf-8";
  }
  if (idempotencyKey) {
    headers["Idempotency-Key"] = idempotencyKey;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "include",
      signal,
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
    const apiError = toApiError({
      apiId,
      path: `${method} ${path}`,
      httpStatus: response.status,
      payload,
    });
    if (!skipAuthIntercept && response.status === 401 && apiError.body) {
      handleAuthApiError(apiError);
    }
    throw apiError;
  }

  if (payload === null && response.status !== 204) {
    throw toApiError({
      apiId,
      path: `${method} ${path}`,
      httpStatus: response.status,
      payload: null,
    });
  }

  return payload as T;
}

type ApiCallOptions = Pick<RequestOptions, "skipAuthIntercept" | "signal">;

export const api = {
  get: <T>(apiId: string, path: string, query?: RequestOptions["query"], options?: ApiCallOptions) =>
    apiRequest<T>({ apiId, path, method: "GET", query, ...options }),
  post: <T>(
    apiId: string,
    path: string,
    body?: unknown,
    idempotencyKey?: string,
    options?: ApiCallOptions,
  ) =>
    apiRequest<T>({
      apiId,
      path,
      method: "POST",
      body,
      idempotencyKey: idempotencyKey ?? newIdempotencyKey(),
      ...options,
    }),
  patch: <T>(
    apiId: string,
    path: string,
    body?: unknown,
    idempotencyKey?: string,
    options?: ApiCallOptions,
  ) =>
    apiRequest<T>({
      apiId,
      path,
      method: "PATCH",
      body,
      idempotencyKey: idempotencyKey ?? newIdempotencyKey(),
      ...options,
    }),
  put: <T>(
    apiId: string,
    path: string,
    body?: unknown,
    idempotencyKey?: string,
    options?: ApiCallOptions,
  ) =>
    apiRequest<T>({
      apiId,
      path,
      method: "PUT",
      body,
      idempotencyKey: idempotencyKey ?? newIdempotencyKey(),
      ...options,
    }),
  delete: <T>(apiId: string, path: string, idempotencyKey?: string, options?: ApiCallOptions) =>
    apiRequest<T>({
      apiId,
      path,
      method: "DELETE",
      idempotencyKey: idempotencyKey ?? newIdempotencyKey(),
      ...options,
    }),
};
