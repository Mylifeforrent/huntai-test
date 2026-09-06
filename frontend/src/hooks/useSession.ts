import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import { queryKeys } from "@/api/queryKeys";
import {
  clearOidcFailureInUrl,
  currentReturnPath,
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

  return {
    phase: redirecting ? ("redirecting" as const) : phase,
    me: meQuery.data?.data,
    error: blockError ?? meQuery.error,
    refetch: meQuery.refetch,
  };
}
