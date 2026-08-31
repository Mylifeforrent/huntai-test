import { Link } from "react-router-dom";
import { TEST_RUN_STATUSES, type ExecutionSource, type TestRunStatus } from "@/api/types";
import { cn } from "@/lib/utils";
import { StatusBadge } from "./StatusBadge";

const ALL = [...TEST_RUN_STATUSES];

export function RunProgressBar({
  status,
  source,
}: {
  status: TestRunStatus | string;
  source?: ExecutionSource | string;
}) {
  const visible = ALL.filter((step) => step !== "WAITING_EXTERNAL" || source === "external_ci");
  const currentIndex = visible.indexOf(status as TestRunStatus);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={status} />
        {source ? <StatusBadge status={source} /> : null}
        {source === "agent" ? (
          <span className="text-xs text-warning">execution_source=agent · 不进质量门禁</span>
        ) : null}
      </div>
      <ol className="flex items-start overflow-x-auto pb-1">
        {visible.map((step, index) => {
          const active = step === status;
          const done = currentIndex >= 0 && index < currentIndex;
          const waitingJump = active && step === "WAITING_APPROVAL";
          const node = (
            <div className="flex min-w-[4.5rem] flex-1 flex-col items-center gap-1.5">
              <span
                className={cn(
                  "flex size-6 items-center justify-center rounded-full font-mono text-[10px] font-medium",
                  active && "bg-primary text-primary-foreground",
                  done && "bg-success text-success-foreground",
                  !active && !done && "border border-border bg-card text-muted-foreground",
                )}
              >
                {index + 1}
              </span>
              <span
                className={cn(
                  "max-w-[5.5rem] text-center font-mono text-[10px] leading-tight",
                  active ? "font-semibold text-foreground" : done ? "text-success" : "text-muted-foreground",
                )}
              >
                {step}
              </span>
            </div>
          );
          return (
            <li key={step} className="flex min-w-0 flex-1 items-start">
              {waitingJump ? (
                <Link to="/approvals" className="block min-w-0 flex-1" title="跳转审批中心">
                  {node}
                </Link>
              ) : (
                <div className="min-w-0 flex-1">{node}</div>
              )}
              {index < visible.length - 1 ? (
                <div className={cn("mt-3 h-px min-w-2 flex-1", index < currentIndex ? "bg-success" : "bg-border")} />
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
