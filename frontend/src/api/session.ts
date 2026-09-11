import type { QueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { ApiError, isNoOrgContext } from "./errors";
import { resetAuthRedirectState, startOidcLogin } from "./authFlow";
import type { SessionMetadata } from "./types";

export {
  clearOidcFailureInUrl,
  currentReturnPath,
  handleAuthApiError,
  handleReauth,
  isAuthRedirectInProgress,
  isOidcFailureRecovery,
  startOidcLogin,
  stripOidcFailureMarker,
  validateReturnPath,
} from "./authFlow";

/** API-006 returns a bare projection, not a ResourceEnvelope-wrapped resource. */
export async function fetchSessionMetadata(): Promise<SessionMetadata> {
  return api.get<SessionMetadata>("API-006", "/api/v1/auth/session", undefined, {
    skipAuthIntercept: true,
  });
}

export async function logoutSession(queryClient: QueryClient): Promise<void> {
  await api.post("API-003", "/api/v1/auth/session/logout", undefined, undefined, {
    skipAuthIntercept: true,
  });
  queryClient.clear();
  resetAuthRedirectState();
  await startOidcLogin("/");
}

export function shouldBlockAuthenticatedShell(error: unknown): boolean {
  return error instanceof ApiError && isNoOrgContext(error);
}
