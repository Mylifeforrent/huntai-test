import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ListEnvelope } from "@/api/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { UndevelopedCallout } from "@/components/domain/UndevelopedCallout";
import { useUrlState } from "@/hooks/useUrlState";
import { cn } from "@/lib/utils";

export function QualityGatePolicyPage() {
  const { get, set } = useUrlState();
  const projectId = get("projectId");
  const [confirmBlock, setConfirmBlock] = useState(false);
  const [saveTried, setSaveTried] = useState(false);
  const [selectedId, setSelectedId] = useState("");

  const query = useQuery({
    queryKey: queryKeys.gatePolicies({ projectId }),
    queryFn: () =>
      api.get<ListEnvelope<Record<string, unknown>>>("API-140", "/api/v1/quality-gate-policies", {
        project_id: projectId,
      }),
    enabled: Boolean(projectId),
  });
  const items = query.data?.data.items ?? [];
  const selected = items.find((item) => String(item.id) === selectedId) ?? items[0];
  const policy = selected ?? {};
  const thresholds = asRecord(policy.thresholds);
  const mode = String(policy.mode ?? "report_only");
  const policyId = String(policy.id ?? "");

  function patchPolicy(nextMode: string) {
    setSaveTried(true);
    if (!policyId) return;
    void api
      .patch(`API-143`, `/api/v1/quality-gate-policies/${policyId}`, {
        mode: nextMode,
        expected_version: policy.version,
        thresholds,
      })
      .catch(() => undefined);
  }

  return (
    <>
      <PageHeader
        title="质量门禁策略"
        description="阈值配置（通过率 / p95 / 错误率）· 仅报告 ⇄ 阻断切换（显式开启）"
        actions={
          <Button variant="link" asChild>
            <Link to="/gates/evaluations">查看评估历史</Link>
          </Button>
        }
      />
      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="projectId（API-140 必填）"
          value={projectId}
          onChange={(event) => set({ projectId: event.target.value })}
          className="max-w-72"
        />
      </div>
      {!projectId ? (
        <Alert>
          <AlertDescription>请填写 projectId。门禁策略按项目查询，前端不本地拼阈值事实。</AlertDescription>
        </Alert>
      ) : (
        <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P11}>
          {items.length === 0 ? (
            <EmptyState title="无门禁策略" />
          ) : (
            <div className="flex flex-col gap-4">
              {items.length > 1 ? (
                <div className="flex flex-wrap gap-2">
                  {items.map((item) => {
                    const id = String(item.id ?? "");
                    return (
                      <Button key={id} size="sm" variant={id === policyId ? "default" : "outline"} onClick={() => setSelectedId(id)}>
                        v{String(item.policy_version ?? "")}
                      </Button>
                    );
                  })}
                </div>
              ) : null}
              <Card>
                <CardHeader>
                  <CardTitle>门禁模式</CardTitle>
                </CardHeader>
                <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <button
                    type="button"
                    onClick={() => patchPolicy("report_only")}
                    className={cn(
                      "rounded-lg border-2 p-4 text-left",
                      mode === "report_only" ? "border-primary bg-accent" : "border-border",
                    )}
                  >
                    <p className="text-sm font-semibold">仅报告</p>
                    <p className="text-xs text-muted-foreground">结论写入 Check Run，不阻塞 PR 合并。</p>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (mode !== "blocking") setConfirmBlock(true);
                    }}
                    className={cn(
                      "rounded-lg border-2 p-4 text-left",
                      mode === "blocking" ? "border-destructive bg-destructive/5" : "border-border",
                    )}
                  >
                    <p className="text-sm font-semibold">阻断模式 · 需显式开启</p>
                    <p className="text-xs text-muted-foreground">门禁不通过时 Check Run 标红，阻止 PR 合并。</p>
                  </button>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>阈值配置</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <Threshold label="最低通过率" suffix="%" value={thresholds.min_pass_rate} />
                  <Threshold label="最大 P95 响应时间" suffix="ms" value={thresholds.max_p95_ms} />
                  <Threshold label="最大错误率" suffix="%" value={thresholds.max_error_rate} />
                  <p className="text-xs text-muted-foreground">
                    仅 script / external_ci 结果进入门禁。execution_source=agent 不进门禁。
                  </p>
                </CardContent>
              </Card>
            </div>
          )}
        </QueryGate>
      )}
      {saveTried ? <UndevelopedCallout apis={PAGE_APIS.P11} action="更新策略 API-143" /> : null}
      <AlertDialog open={confirmBlock} onOpenChange={setConfirmBlock}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>切换为阻断模式</AlertDialogTitle>
            <AlertDialogDescription>
              开启后，门禁不通过的 TestRun 将阻止 GitHub Check Run 变为绿色，影响 PR 合并。须显式确认。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={() => patchPolicy("blocking")}>确认开启阻断</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

function Threshold({ label, suffix, value }: { label: string; suffix: string; value: unknown }) {
  return (
    <div className="flex items-center gap-4">
      <Label className="w-48">{label}</Label>
      <span className="font-mono text-sm">{value == null ? "—" : String(value)}</span>
      <span className="text-xs text-muted-foreground">{suffix}</span>
    </div>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}
