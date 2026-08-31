import { Construction } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { ApiDescriptor } from "@/api/catalog";
import { ApiError } from "@/api/errors";

export function UndevelopedCallout({
  apis,
  error,
  action,
  compact,
}: {
  apis: readonly ApiDescriptor[];
  error?: unknown;
  action?: string;
  compact?: boolean;
}) {
  const apiError = error instanceof ApiError ? error : null;
  if (compact) {
    return (
      <div className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning-foreground px-3 py-2 text-xs text-warning">
        <Construction className="mt-0.5 size-3.5 shrink-0" />
        <div className="flex min-w-0 flex-col gap-0.5">
          <p className="font-medium">未开发</p>
          {action ? <p>{action}依赖的后端接口尚未实现。</p> : null}
          {apiError ? (
            <p className="font-mono">
              {apiError.apiId}
              {apiError.httpStatus ? ` · HTTP ${apiError.httpStatus}` : ""}
            </p>
          ) : (
            <p className="font-mono">{apis.map((item) => item.id).join(" · ")}</p>
          )}
        </div>
      </div>
    );
  }
  return (
    <Alert variant="warning">
      <div className="flex items-start gap-2">
        <Construction className="mt-0.5 size-4 shrink-0" />
        <div className="min-w-0">
          <AlertTitle>未开发</AlertTitle>
          <AlertDescription>
            {action ? <p className="mb-1">{action}依赖的后端接口尚未实现，前端不会伪造该功能。</p> : null}
            {apiError ? (
              <p className="mb-1 font-mono text-xs">
                {apiError.apiId} · {apiError.path}
                {apiError.httpStatus ? ` · HTTP ${apiError.httpStatus}` : ""}
              </p>
            ) : null}
            <ul className="flex flex-col gap-0.5 font-mono text-xs">
              {apis.map((api) => (
                <li key={api.id}>
                  {api.id} {api.method} {api.path} — {api.summary}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </div>
      </div>
    </Alert>
  );
}
