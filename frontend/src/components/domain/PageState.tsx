import type { ReactNode } from "react";
import { Inbox } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, isUndeveloped } from "@/api/errors";
import type { ApiDescriptor } from "@/api/catalog";
import { cn } from "@/lib/utils";
import { UndevelopedCallout } from "./UndevelopedCallout";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function LoadingState({ rows = 4 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-3">
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className="h-16 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({ title, hint, compact }: { title: string; hint?: string; compact?: boolean }) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-2 rounded-lg border border-dashed bg-muted/40 text-center",
        compact ? "px-4 py-6" : "px-6 py-10",
      )}
    >
      <div className={cn("flex items-center justify-center rounded-full bg-muted", compact ? "size-8" : "size-9")}>
        <Inbox className="size-4 text-muted-foreground" />
      </div>
      <p className="text-sm font-medium">{title}</p>
      {hint ? <p className="max-w-md text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (error instanceof ApiError && error.kind === "permission") {
    return (
      <Alert variant="destructive">
        <AlertTitle>无权限</AlertTitle>
        <AlertDescription>{error.message}</AlertDescription>
      </Alert>
    );
  }
  if (error instanceof ApiError && error.kind === "not_found") {
    return (
      <Alert>
        <AlertTitle>资源不存在</AlertTitle>
        <AlertDescription>当前资源不可见或不存在（不区分跨租户与缺失）。</AlertDescription>
      </Alert>
    );
  }
  return (
    <Alert variant="destructive">
      <AlertTitle>请求失败</AlertTitle>
      <AlertDescription className="flex flex-col gap-2">
        <span>{error instanceof Error ? error.message : "未知错误"}</span>
        {onRetry ? (
          <Button size="sm" variant="outline" onClick={onRetry}>
            重试
          </Button>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}

export function QueryGate({
  isPending,
  error,
  apis,
  children,
}: {
  isPending: boolean;
  error: unknown;
  apis: readonly ApiDescriptor[];
  children: ReactNode;
}) {
  if (isPending) {
    return <LoadingState />;
  }
  if (isUndeveloped(error) || error) {
    if (isUndeveloped(error) || (error instanceof ApiError && error.kind === "undeveloped")) {
      return <UndevelopedCallout apis={apis} error={error} />;
    }
    return <ErrorState error={error} />;
  }
  return <>{children}</>;
}

/** Write-command outcome: undeveloped vs business/network. Never a fake success. */
export function CommandFeedback({
  error,
  apis,
  action,
}: {
  error: unknown;
  apis: readonly ApiDescriptor[];
  action: string;
}) {
  if (!error) {
    return null;
  }
  if (isUndeveloped(error)) {
    return <UndevelopedCallout apis={apis} error={error} action={action} />;
  }
  return <ErrorState error={error} />;
}
