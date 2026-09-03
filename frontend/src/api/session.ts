import type { QueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { ApiError, isNoOrgContext } from "./errors";
import { resetAuthRedirectState, startOidcLogin } from "./authFlow";

export {
  currentReturnPath,
  handleAuthApiError,
  handleReauth,
  isAuthRedirectInProgress,
  startOidcLogin,
  validateReturnPath,
} from "./authFlow";

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
