import { Outlet } from "react-router-dom";
import { ErrorState, LoadingState } from "@/components/domain/PageState";
import { useSession } from "@/hooks/useSession";

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
    return (
      <div className="flex h-full min-h-screen items-center justify-center bg-background p-6">
        <div className="w-full max-w-lg">
          <ErrorState error={session.error} onRetry={() => void session.refetch()} />
        </div>
      </div>
    );
  }

  return <Outlet />;
}
