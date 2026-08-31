const DEFAULT_BASE = "/api/v1";

export function apiBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || DEFAULT_BASE;
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
