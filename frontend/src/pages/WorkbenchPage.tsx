import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Play } from "lucide-react";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import { isUndeveloped } from "@/api/errors";
import type { ResourceEnvelope, WorkbenchProjection } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader, EmptyState, ErrorState } from "@/components/domain/PageState";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { RiskBadge } from "@/components/domain/RiskBadge";
import { UndevelopedCallout } from "@/components/domain/UndevelopedCallout";
import { asRecord, tokenRemainingProjection } from "@/lib/utils";

export function WorkbenchPage() {
  const workbench = useQuery({
    queryKey: queryKeys.workbench,
    queryFn: () => api.get<ResourceEnvelope<WorkbenchProjection>>("API-020", "/api/v1/workbench"),
  });
  const quota = useQuery({
    queryKey: queryKeys.orgQuota,
    queryFn: () => api.get<ResourceEnvelope<unknown>>("API-017", "/api/v1/org-quotas/current"),
  });

  const data = workbench.data?.data;
  const pending = Array.isArray(data?.pending_approvals) ? data.pending_approvals : [];
  const runs = Array.isArray(data?.active_runs) ? data.active_runs : [];
  const gates = Array.isArray(data?.gate_anomalies) ? data.gate_anomalies : [];
  const workbenchBlocked = Boolean(workbench.error) && !workbench.isPending;
  const workbenchUndeveloped = isUndeveloped(workbench.error);
  const quotaUndeveloped = isUndeveloped(quota.error);
  const remaining = tokenRemainingProjection(quota.data?.data);

  return (
    <>
      <PageHeader
        title="工作台"
        description="待审批 · 进行中 TestRun · 门禁异常 · 部门预算余量"
        actions={
          <Button asChild>
            <Link to="/test-center/kickoff">
              <Play />
              发起执行
            </Link>
          </Button>
        }
      />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="待审批"
          value={workbenchBlocked ? undefined : String(pending.length)}
          hint="API-020 pending_approvals"
          loading={workbench.isPending}
          undeveloped={workbenchUndeveloped}
        />
        <Stat
          label="执行中"
          value={workbenchBlocked ? undefined : String(runs.length)}
          hint="等待态不得折叠"
          loading={workbench.isPending}
          undeveloped={workbenchUndeveloped}
        />
        <Stat
          label="门禁异常"
          value={workbenchBlocked ? undefined : String(gates.length)}
          hint="24h 未处理"
          loading={workbench.isPending}
          undeveloped={workbenchUndeveloped}
        />
        <Stat
          label="Token 余量"
          value={remaining}
          hint="API-017 token_remaining"
          loading={quota.isPending}
          undeveloped={quotaUndeveloped}
        />
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>待审批</CardTitle>
            <Link to="/approvals" className="text-xs text-primary">
              查看全部
            </Link>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {workbench.isPending ? <Skeleton className="h-20 w-full" /> : null}
            {workbenchUndeveloped ? (
              <UndevelopedCallout compact apis={PAGE_APIS.P01.filter((item) => item.id === "API-020")} action="待审批列表" />
            ) : null}
            {workbenchBlocked && !workbenchUndeveloped ? <ErrorState error={workbench.error} /> : null}
            {!workbench.isPending && !workbenchBlocked && pending.length === 0 ? (
              <EmptyState compact title="无待审批" hint="空集是服务端下发。" />
            ) : null}
            {pending.map((item, index) => {
              const row = asRecord(item);
              return (
                <Link key={String(row.id ?? index)} to="/approvals" className="rounded-md border p-3 hover:bg-muted/40">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-muted-foreground">{String(row.id ?? "")}</span>
                    {typeof row.risk === "string" ? <RiskBadge level={row.risk} /> : null}
                  </div>
                  <p className="truncate text-sm">{String(row.target ?? row.action ?? "审批项")}</p>
                </Link>
              );
            })}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>进行中 TestRun</CardTitle>
            <Link to="/test-center/runs" className="text-xs text-primary">
              查看全部
            </Link>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {workbench.isPending ? <Skeleton className="h-20 w-full" /> : null}
            {workbenchUndeveloped ? (
              <UndevelopedCallout compact apis={PAGE_APIS.P01.filter((item) => item.id === "API-020")} action="进行中 TestRun" />
            ) : null}
            {workbenchBlocked && !workbenchUndeveloped ? <ErrorState error={workbench.error} /> : null}
            {!workbench.isPending && !workbenchBlocked && runs.length === 0 ? (
              <EmptyState compact title="无进行中运行" hint="WAITING_* 态不得从本列折叠。" />
            ) : null}
            {runs.map((item, index) => {
              const row = asRecord(item);
              return (
                <Link
                  key={String(row.id ?? index)}
                  to={`/test-center/runs/${String(row.id ?? "")}`}
                  className="rounded-md border p-3 hover:bg-muted/40"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs">{String(row.id ?? "")}</span>
                    {typeof row.status === "string" ? <StatusBadge status={row.status} /> : null}
                  </div>
                      {typeof row.dwell_seconds === "number" ? (
                        <p className="text-xs text-muted-foreground">滞留 {row.dwell_seconds}s（服务端投影）</p>
                      ) : (
                        <p className="text-xs text-muted-foreground">滞留时长由服务端下发，前端不推演</p>
                      )}
                </Link>
              );
            })}
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function Stat({
  label,
  value,
  hint,
  loading,
  undeveloped,
}: {
  label: string;
  value?: string;
  hint: string;
  loading?: boolean;
  undeveloped?: boolean;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1">
        <p className="text-xs text-muted-foreground">{label}</p>
        {loading ? <Skeleton className="h-8 w-16" /> : null}
        {undeveloped ? <p className="text-sm font-medium text-warning">未开发</p> : null}
        {!loading && !undeveloped ? (
          <p className="font-mono text-2xl font-bold tabular-nums">{value ?? "未返回"}</p>
        ) : null}
        <p className="text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}

