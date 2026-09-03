import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type {
  ListEnvelope,
  QualityGatePolicyDetail,
  QualityGatePolicyListItem,
  ResourceEnvelope,
} from "@/api/types";
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
import { CommandFeedback, PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { useUrlState } from "@/hooks/useUrlState";
import { useSession } from "@/hooks/useSession";
import { cn } from "@/lib/utils";

const DEFAULT_THRESHOLDS = {
  min_pass_rate: 95,
  max_p95_ms: 500,
  max_error_rate: 1,
};

export function QualityGatePolicyPage() {
  const queryClient = useQueryClient();
  const session = useSession();
  const { get, set } = useUrlState();
  const projectId = get("projectId");
  const modeFilter = get("mode");
  const cursor = get("cursor");
  const selectedId = get("policy") || "";

  const [confirmBlock, setConfirmBlock] = useState(false);
  const [confirmCreateBlock, setConfirmCreateBlock] = useState(false);
  const [createError, setCreateError] = useState<unknown>(null);
  const [patchError, setPatchError] = useState<unknown>(null);
  const [createMode, setCreateMode] = useState<"report_only" | "blocking">("report_only");
  const [minPassRate, setMinPassRate] = useState(String(DEFAULT_THRESHOLDS.min_pass_rate));
  const [maxP95Ms, setMaxP95Ms] = useState(String(DEFAULT_THRESHOLDS.max_p95_ms));
  const [maxErrorRate, setMaxErrorRate] = useState(String(DEFAULT_THRESHOLDS.max_error_rate));
  const [scopeJson, setScopeJson] = useState("{}");
  const [editMinPassRate, setEditMinPassRate] = useState("");
  const [editMaxP95Ms, setEditMaxP95Ms] = useState("");
  const [editMaxErrorRate, setEditMaxErrorRate] = useState("");

  const canWrite =
    session.me?.memberships.some(
      (membership) =>
        membership.project_id === projectId &&
        (membership.role === "owner" || membership.role === "admin"),
    ) ?? false;

  const listQuery = useQuery({
    queryKey: queryKeys.gatePolicies({ projectId, mode: modeFilter, cursor }),
    queryFn: () =>
      api.get<ListEnvelope<QualityGatePolicyListItem>>("API-140", "/api/v1/quality-gate-policies", {
        project_id: projectId,
        mode: modeFilter || undefined,
        cursor: cursor || undefined,
      }),
    enabled: Boolean(projectId),
  });
  const items = listQuery.data?.data.items ?? [];

  const activePolicyId = selectedId || (items[0]?.id ?? "");
  const listItem = items.find((item) => item.id === activePolicyId) ?? items[0];

  const detailQuery = useQuery({
    queryKey: ["quality-gate-policy", activePolicyId],
    queryFn: () =>
      api.get<ResourceEnvelope<QualityGatePolicyDetail>>(
        "API-141",
        `/api/v1/quality-gate-policies/${activePolicyId}`,
      ),
    enabled: Boolean(activePolicyId),
  });
  const detail = detailQuery.data?.data ?? listItem;

  useEffect(() => {
    if (!detail) return;
    setEditMinPassRate(String(detail.thresholds.min_pass_rate));
    setEditMaxP95Ms(String(detail.thresholds.max_p95_ms));
    setEditMaxErrorRate(String(detail.thresholds.max_error_rate));
  }, [detail?.id, detail?.policy_version, detail?.version]);

  const mode = String(detail?.mode ?? "report_only");
  const policyId = String(detail?.id ?? "");

  const invalidatePolicies = () => {
    void queryClient.invalidateQueries({ queryKey: ["quality-gate-policies"] });
    if (policyId) {
      void queryClient.invalidateQueries({ queryKey: ["quality-gate-policy", policyId] });
    }
  };

  const createPolicy = useMutation({
    mutationFn: (confirmBlocking: boolean) => {
      let scope: Record<string, unknown> = {};
      try {
        scope = JSON.parse(scopeJson) as Record<string, unknown>;
        if (typeof scope !== "object" || scope === null || Array.isArray(scope)) {
          return Promise.reject(new Error("scope must be a JSON object"));
        }
      } catch {
        return Promise.reject(new Error("invalid scope JSON"));
      }
      const body: Record<string, unknown> = {
        project_id: projectId,
        mode: createMode,
        scope,
        thresholds: {
          min_pass_rate: Number(minPassRate),
          max_p95_ms: Number(maxP95Ms),
          max_error_rate: Number(maxErrorRate),
        },
      };
      if (createMode === "blocking") {
        body.confirm_blocking = confirmBlocking;
      }
      return api.post<ResourceEnvelope<QualityGatePolicyDetail>>(
        "API-142",
        "/api/v1/quality-gate-policies",
        body,
      );
    },
    onMutate: () => setCreateError(null),
    onSuccess: (response) => {
      invalidatePolicies();
      set({ policy: response.data.id });
      setCreateMode("report_only");
      setScopeJson("{}");
    },
    onError: (error) => setCreateError(error),
  });

  const patchPolicy = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.patch<ResourceEnvelope<QualityGatePolicyListItem>>(
        "API-143",
        `/api/v1/quality-gate-policies/${policyId}`,
        body,
      ),
    onMutate: () => setPatchError(null),
    onSuccess: () => invalidatePolicies(),
    onError: (error) => setPatchError(error),
  });

  function patchMode(nextMode: string, confirmBlocking = false) {
    if (!detail || !policyId) return;
    const body: Record<string, unknown> = {
      expected_version: detail.version,
      mode: nextMode,
    };
    if (nextMode === "blocking" && confirmBlocking) {
      body.confirm_blocking = true;
    }
    patchPolicy.mutate(body);
  }

  function saveThresholds() {
    if (!detail || !policyId) return;
    patchPolicy.mutate({
      expected_version: detail.version,
      thresholds: {
        min_pass_rate: Number(editMinPassRate),
        max_p95_ms: Number(editMaxP95Ms),
        max_error_rate: Number(editMaxErrorRate),
      },
    });
  }

  const modeFilterOptions = useMemo(
    () => [
      { value: "", label: "全部模式" },
      { value: "report_only", label: "仅报告" },
      { value: "blocking", label: "阻断" },
    ],
    [],
  );

  return (
    <>
      <PageHeader
        title="质量门禁策略"
        description="配置阈值与模式。保存策略不等于 TestRun 已通过门禁；未评估不得视为通过。"
        actions={
          <Button variant="link" asChild>
            <Link to="/gates/evaluations">查看评估历史</Link>
          </Button>
        }
      />
      <Alert>
        <AlertDescription>
          门禁策略仅定义评估规则。创建或更新策略不会生成 GateEvaluation，也不会使任何 TestRun 通过门禁。缺少评估记录时不得视为通过。
        </AlertDescription>
      </Alert>
      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="projectId（API-140 必填）"
          value={projectId}
          onChange={(event) => set({ projectId: event.target.value, policy: "", cursor: "" })}
          className="max-w-72"
        />
        <select
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          value={modeFilter}
          onChange={(event) => set({ mode: event.target.value, cursor: "" })}
          disabled={!projectId}
        >
          {modeFilterOptions.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>
      {!projectId ? (
        <Alert>
          <AlertDescription>请填写 projectId。门禁策略按项目查询，前端不本地拼阈值事实。</AlertDescription>
        </Alert>
      ) : (
        <QueryGate isPending={listQuery.isPending} error={listQuery.error} apis={PAGE_APIS.P11}>
          {canWrite ? (
            <Card>
              <CardHeader>
                <CardTitle>创建策略</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <div className="grid gap-3 sm:grid-cols-3">
                  <ThresholdInput label="最低通过率" suffix="%" value={minPassRate} onChange={setMinPassRate} />
                  <ThresholdInput label="最大 P95" suffix="ms" value={maxP95Ms} onChange={setMaxP95Ms} />
                  <ThresholdInput label="最大错误率" suffix="%" value={maxErrorRate} onChange={setMaxErrorRate} />
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant={createMode === "report_only" ? "default" : "outline"}
                    onClick={() => setCreateMode("report_only")}
                  >
                    仅报告
                  </Button>
                  <Button
                    size="sm"
                    variant={createMode === "blocking" ? "destructive" : "outline"}
                    onClick={() => setConfirmCreateBlock(true)}
                  >
                    阻断模式
                  </Button>
                </div>
                <div className="flex flex-col gap-2">
                  <Label>scope（JSON 对象，按后端存储）</Label>
                  <textarea
                    className="min-h-20 rounded-md border border-input bg-background px-3 py-2 font-mono text-sm"
                    value={scopeJson}
                    onChange={(event) => setScopeJson(event.target.value)}
                    placeholder="{}"
                  />
                </div>
                <Button
                  disabled={createPolicy.isPending}
                  onClick={() => {
                    if (createMode === "blocking") {
                      setConfirmCreateBlock(true);
                      return;
                    }
                    createPolicy.mutate(false);
                  }}
                >
                  创建策略（API-142）
                </Button>
                <p className="text-xs text-muted-foreground">
                  创建成功仅表示策略已保存，不代表任何 TestRun 已通过门禁。
                </p>
              </CardContent>
            </Card>
          ) : null}

          {items.length === 0 ? (
            <EmptyState title="无门禁策略" hint="管理员可创建项目门禁策略。空列表不是错误。" />
          ) : (
            <div className="flex flex-col gap-4">
              {items.length > 1 ? (
                <div className="flex flex-wrap gap-2">
                  {items.map((item) => (
                    <Button
                      key={item.id}
                      size="sm"
                      variant={item.id === activePolicyId ? "default" : "outline"}
                      onClick={() => set({ policy: item.id })}
                    >
                      v{item.policy_version}
                    </Button>
                  ))}
                </div>
              ) : null}
              {detail ? (
                <>
                  <Card>
                    <CardHeader>
                      <CardTitle>
                        门禁模式 · policy_version {detail.policy_version} · CAS version {detail.version}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <button
                        type="button"
                        disabled={!canWrite || patchPolicy.isPending}
                        onClick={() => patchMode("report_only")}
                        className={cn(
                          "rounded-lg border-2 p-4 text-left",
                          mode === "report_only" ? "border-primary bg-accent" : "border-border",
                          !canWrite && "opacity-60",
                        )}
                      >
                        <p className="text-sm font-semibold">仅报告</p>
                        <p className="text-xs text-muted-foreground">记录评估结论，不阻塞合并（评估管线 M2）。</p>
                      </button>
                      <button
                        type="button"
                        disabled={!canWrite || patchPolicy.isPending}
                        onClick={() => {
                          if (mode !== "blocking") setConfirmBlock(true);
                        }}
                        className={cn(
                          "rounded-lg border-2 p-4 text-left",
                          mode === "blocking" ? "border-destructive bg-destructive/5" : "border-border",
                          !canWrite && "opacity-60",
                        )}
                      >
                        <p className="text-sm font-semibold">阻断模式 · 需显式开启</p>
                        <p className="text-xs text-muted-foreground">切换为阻断须确认；不等于 TestRun 已通过。</p>
                      </button>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader>
                      <CardTitle>阈值配置</CardTitle>
                    </CardHeader>
                    <CardContent className="flex flex-col gap-3">
                      {canWrite ? (
                        <>
                          <ThresholdInput
                            label="最低通过率"
                            suffix="%"
                            value={editMinPassRate}
                            onChange={setEditMinPassRate}
                          />
                          <ThresholdInput
                            label="最大 P95 响应时间"
                            suffix="ms"
                            value={editMaxP95Ms}
                            onChange={setEditMaxP95Ms}
                          />
                          <ThresholdInput
                            label="最大错误率"
                            suffix="%"
                            value={editMaxErrorRate}
                            onChange={setEditMaxErrorRate}
                          />
                          <Button disabled={patchPolicy.isPending} onClick={saveThresholds}>
                            保存阈值（API-143）
                          </Button>
                        </>
                      ) : (
                        <>
                          <Threshold label="最低通过率" suffix="%" value={detail.thresholds.min_pass_rate} />
                          <Threshold label="最大 P95 响应时间" suffix="ms" value={detail.thresholds.max_p95_ms} />
                          <Threshold label="最大错误率" suffix="%" value={detail.thresholds.max_error_rate} />
                        </>
                      )}
                      <p className="text-xs text-muted-foreground">
                        仅 script / external_ci 结果进入门禁评估（M2）。execution_source=agent 不进门禁。
                      </p>
                    </CardContent>
                  </Card>
                  {detailQuery.data?.data.scope ? (
                    <Card>
                      <CardHeader>
                        <CardTitle>scope（API-141）</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
                          {JSON.stringify(detailQuery.data.data.scope, null, 2)}
                        </pre>
                      </CardContent>
                    </Card>
                  ) : null}
                </>
              ) : null}
            </div>
          )}
        </QueryGate>
      )}
      <CommandFeedback error={createError} apis={PAGE_APIS.P11} action="创建门禁策略 API-142" />
      <CommandFeedback error={patchError} apis={PAGE_APIS.P11} action="更新门禁策略 API-143" />
      <AlertDialog open={confirmBlock} onOpenChange={setConfirmBlock}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>切换为阻断模式</AlertDialogTitle>
            <AlertDialogDescription>
              开启阻断模式后，未来门禁评估不通过时可能阻塞 CI（M2）。此操作不等于任何 TestRun 已通过门禁。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={() => patchMode("blocking", true)}>确认开启阻断</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <AlertDialog open={confirmCreateBlock} onOpenChange={setConfirmCreateBlock}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>创建阻断模式策略</AlertDialogTitle>
            <AlertDialogDescription>
              创建 blocking 策略须显式确认。保存策略不等于 TestRun 已通过门禁。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setCreateMode("blocking");
                createPolicy.mutate(true);
                setConfirmCreateBlock(false);
              }}
            >
              确认创建阻断策略
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

function ThresholdInput({
  label,
  suffix,
  value,
  onChange,
}: {
  label: string;
  suffix: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <Label>{label}</Label>
      <div className="flex items-center gap-2">
        <Input value={value} onChange={(event) => onChange(event.target.value)} className="max-w-32" />
        <span className="text-xs text-muted-foreground">{suffix}</span>
      </div>
    </div>
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
