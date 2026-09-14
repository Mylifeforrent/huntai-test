import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Play } from "lucide-react";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import { isUndeveloped } from "@/api/errors";
import type { OrgQuotaCurrent, ResourceEnvelope, WorkbenchProjection } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader, EmptyState, ErrorState } from "@/components/domain/PageState";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { UndevelopedCallout } from "@/components/domain/UndevelopedCallout";
import { formatServerScalar } from "@/lib/utils";

export function WorkbenchPage() {
  const workbench = useQuery({
    queryKey: queryKeys.workbench,
    queryFn: () => api.get<ResourceEnvelope<WorkbenchProjection>>("API-020", "/api/v1/workbench"),
  });
  const quota = useQuery({
    queryKey: queryKeys.orgQuota,
    queryFn: () => api.get<ResourceEnvelope<OrgQuotaCurrent>>("API-017", "/api/v1/org-quotas/current"),
  });

  const data = workbench.data?.data;
  const pending = data?.pending_approvals ?? [];
  const runs = data?.active_runs ?? [];
  const gates = data?.gate_anomalies ?? [];
  const workbenchBlocked = Boolean(workbench.error) && !workbench.isPending;
  const workbenchUndeveloped = isUndeveloped(workbench.error);
  const quotaUndeveloped = isUndeveloped(quota.error);
  const workbenchRemaining = formatServerScalar(data?.quota?.token_remaining);
  const corroborationRemaining = formatServerScalar(quota.data?.data?.token_remaining);
  const remaining = workbenchRemaining ?? corroborationRemaining;

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
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-4">
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
          hint="API-020 gate_anomalies"
          loading={workbench.isPending}
          undeveloped={workbenchUndeveloped}
        />
        <Stat
          label="Token 余量"
          value={remaining}
          hint="API-020 quota.token_remaining（API-017 佐证）"
          loading={workbench.isPending || quota.isPending}
          undeveloped={workbenchUndeveloped && quotaUndeveloped}
        />
      </div>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
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
            {pending.map((item) => (
              <Link key={item.id} to="/approvals" className="rounded-md border p-3 hover:bg-muted/40">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-muted-foreground">{item.id}</span>
                  <StatusBadge status={item.action_type} />
                </div>
                <p className="truncate text-sm">{item.action_type}</p>
                <p className="text-xs text-muted-foreground">到期 {item.expires_at}</p>
              </Link>
            ))}
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
            {runs.map((item) => (
              <Link
                key={item.id}
                to={`/test-center/runs/${item.id}`}
                className="rounded-md border p-3 hover:bg-muted/40"
              >
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs">{item.id}</span>
                  <StatusBadge status={item.status} />
                </div>
                {typeof item.dwell_seconds === "number" ? (
                  <p className="text-xs text-muted-foreground">滞留 {item.dwell_seconds}s（服务端投影）</p>
                ) : (
                  <p className="text-xs text-muted-foreground">滞留时长由服务端下发，前端不推演</p>
                )}
              </Link>
            ))}
          </CardContent>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>门禁异常</CardTitle>
            <Link to="/test-center/runs" className="text-xs text-primary">
              查看全部
            </Link>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {workbench.isPending ? <Skeleton className="h-20 w-full" /> : null}
            {workbenchUndeveloped ? (
              <UndevelopedCallout compact apis={PAGE_APIS.P01.filter((item) => item.id === "API-020")} action="门禁异常" />
            ) : null}
            {workbenchBlocked && !workbenchUndeveloped ? <ErrorState error={workbench.error} /> : null}
            {!workbench.isPending && !workbenchBlocked && gates.length === 0 ? (
              <EmptyState compact title="无门禁异常" hint="空集是服务端下发。" />
            ) : null}
            {gates.map((item) => (
              <Link
                key={`${item.kind}-${item.test_run_id ?? item.gate_evaluation_id ?? "unknown"}`}
                to={`/test-center/runs/${item.test_run_id}`}
                className="rounded-md border p-3 hover:bg-muted/40"
              >
                <div className="flex items-center gap-2">
                  <StatusBadge status={item.kind} />
                  {item.test_run_id ? (
                    <span className="font-mono text-xs text-muted-foreground">{item.test_run_id}</span>
                  ) : null}
                </div>
                {item.unevaluated_reason ? (
                  <p className="text-xs text-muted-foreground">未评估原因 {item.unevaluated_reason}</p>
                ) : item.result ? (
                  <p className="text-xs text-muted-foreground">评估结果 {item.result}</p>
                ) : null}
              </Link>
            ))}
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
