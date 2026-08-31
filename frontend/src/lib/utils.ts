import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

/** Command/query envelopes: ResourceEnvelope.data.id or CommandReceipt.resource_id. */
export function extractResourceId(payload: unknown): string | undefined {
  const row = asRecord(payload);
  if (typeof row.resource_id === "string" && row.resource_id) {
    return row.resource_id;
  }
  const data = asRecord(row.data);
  if (typeof data.id === "string" && data.id) {
    return data.id;
  }
  if (typeof data.resource_id === "string" && data.resource_id) {
    return data.resource_id;
  }
  if (typeof row.id === "string" && row.id) {
    return row.id;
  }
  return undefined;
}

export function formatServerScalar(value: unknown): string | undefined {
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  if (typeof value === "string" && value) {
    return value;
  }
  return undefined;
}

/** Display only the server token_remaining projection. Never budget - reserved - consumed. */
export function tokenRemainingProjection(data: unknown): string | undefined {
  return formatServerScalar(asRecord(data).token_remaining);
}
