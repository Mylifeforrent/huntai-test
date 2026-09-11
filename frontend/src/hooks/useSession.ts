import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { ApiError, isRequireReauth } from "@/api/errors";
import { queryKeys } from "@/api/queryKeys";
import {
  clearOidcFailureInUrl,
  currentReturnPath,
  fetchSessionMetadata,
  isAuthRedirectInProgress,
  isOidcFailureRecovery,
  shouldBlockAuthenticatedShell,
  startOidcLogin,
} from "@/api/session";
import type { MeProjection, ResourceEnvelope } from "@/api/types";

export type SessionPhase = "bootstrapping" | "redirecting" | "ready" | "blocked";

export function useSession() {
  const [phase, setPhase] = useState<SessionPhase>("bootstrapping");
  const [blockError, setBlockError] = useState<unknown>(null);

  const meQuery = useQuery({
    queryKey: queryKeys.me,
    queryFn: () =>
      api.get<ResourceEnvelope<MeProjection>>("API-005", "/api/v1/me", undefined, {
        skipAuthIntercept: true,
      }),
    retry: false,
  });

  useEffect(() => {
    if (meQuery.isPending) {
      setPhase("bootstrapping");
      return;
    }
    if (meQuery.isSuccess) {
      clearOidcFailureInUrl();
      setPhase("ready");
      setBlockError(null);
      return;
    }
    if (!meQuery.error) {
      return;
    }

    const error = meQuery.error;

    // HT-AUTH-002: the L3+ step-up window elapsed. The shell stays browsable —
    // only the privileged command needs re-auth — so surface the notice instead
    // of blocking the whole application.
    if (error instanceof ApiError && isRequireReauth(error)) {
      setBlockError(null);
      setPhase("ready");
      return;
    }

    if (shouldBlockAuthenticatedShell(error)) {
      setBlockError(error);
      setPhase("blocked");
      return;
    }

    if (isOidcFailureRecovery() || (error instanceof ApiError && error.body?.code === "HT-AUTH-003")) {
      setBlockError(error);
      setPhase("blocked");
      return;
    }

    if (error instanceof ApiError && error.body?.code === "HT-AUTH-001") {
      setPhase("redirecting");
      void startOidcLogin(currentReturnPath()).catch((redirectError) => {
        setBlockError(redirectError);
        setPhase("blocked");
      });
      return;
    }

    setBlockError(error);
    setPhase("blocked");
  }, [meQuery.isPending, meQuery.isSuccess, meQuery.error]);

  const redirecting = phase === "redirecting" || isAuthRedirectInProgress();
  const exposedPhase = redirecting ? ("redirecting" as const) : phase;

  return {
    phase: exposedPhase,
    me: meQuery.data?.data,
    // Only meaningful when the shell is not usable: a stale query error must not
    // be reported as a live error once the session is ready (e.g. HT-AUTH-002).
    error: exposedPhase === "ready" ? null : (blockError ?? meQuery.error),
    refetch: meQuery.refetch,
  };
}

/**
 * API-006 probe for the step-up hint. Read-only: it never starts a redirect, so
 * it is safe to mount outside the session phase machine. The hint comes from the
 * server's own boolean — no client-side expiry threshold is invented.
 */
export function useReauthRequired(): boolean {
  const sessionQuery = useQuery({
    queryKey: queryKeys.session,
    queryFn: () => fetchSessionMetadata(),
    retry: false,
  });
  return sessionQuery.data?.reauth_required === true;
}
