import { Outlet } from "react-router-dom";
import { ErrorState, LoadingState } from "@/components/domain/PageState";
import { SsoRecoveryPanel } from "@/components/layout/SsoRecoveryPanel";
import { useSession } from "@/hooks/useSession";
import { isOidcFailureRecovery } from "@/api/session";
import { ApiError } from "@/api/errors";

export function SessionGate() {
  const session = useSession();

  if (session.phase === "bootstrapping" || session.phase === "redirecting") {
    return (
      <div className="flex h-full min-h-screen items-center justify-center bg-background p-6">
        <LoadingState rows={3} />
      </div>
    );
  }

  if (session.phase === "blocked") {
    const showSsoRecovery =
      isOidcFailureRecovery() ||
      (session.error instanceof ApiError && session.error.body?.code === "HT-AUTH-003");
    return (
      <div className="flex h-full min-h-screen items-center justify-center bg-background p-6">
        <div className="w-full max-w-lg">
          {showSsoRecovery ? (
            <SsoRecoveryPanel />
          ) : (
            <ErrorState error={session.error} onRetry={() => void session.refetch()} />
          )}
        </div>
      </div>
    );
  }

  return <Outlet />;
}
