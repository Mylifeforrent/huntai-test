import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { newIdempotencyKey } from "@/api/apiConfig";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ListEnvelope, ResourceEnvelope } from "@/api/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
import { CommandFeedback, MutateOnly, PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { useUrlState } from "@/hooks/useUrlState";
import { asRecord } from "@/lib/utils";
import { cn } from "@/lib/utils";

const READINESS_TONE: Record<string, string> = {
  green: "bg-success",
  yellow: "bg-warning",
  red: "bg-destructive",
};

const TERMINAL_READY = new Set(["READY", "CANCELLED"]);
const RETRYABLE = new Set(["FAILED_RETRYABLE"]);

export function ReleaseTaskPage() {
  const queryClient = useQueryClient();
  const { get, set } = useUrlState();
  const projectId = get("projectId");
  const jiraVersionRef = get("jiraVersionRef");
  const selectedId = get("id");
  const [pushOpen, setPushOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [commandError, setCommandError] = useState<unknown>(null);
  const [pushPreviewId, setPushPreviewId] = useState<string | null>(null);

  const list = useQuery({
    queryKey: queryKeys.releaseTasks({ projectId }),
    queryFn: () =>
      api.get<ListEnvelope<Record<string, unknown>>>("API-150", "/api/v1/release-tasks", {
        project_id: projectId,
      }),
    enabled: Boolean(projectId),
  });
  const items = list.data?.data.items ?? [];
  const current = items.find((item) => String(item.id) === selectedId) ?? items[0];
  const taskId = current ? String(current.id ?? "") : "";

  const detail = useQuery({
    queryKey: ["release-tasks", taskId, "detail"],
    enabled: Boolean(taskId),
    queryFn: () =>
      api.get<ResourceEnvelope<Record<string, unknown>>>(
        "API-151",
        `/api/v1/release-tasks/${taskId}`,
      ),
  });
  const detailData = detail.data?.data ?? {};
  const currentStatus = String(detailData.status ?? current?.status ?? "");
  const currentVersion =
    typeof detailData.version === "number"
      ? detailData.version
      : Number(current?.version ?? 0) || 0;

  const readiness = useQuery({
    queryKey: ["release-tasks", taskId, "readiness"],
    queryFn: () =>
      api.get<ResourceEnvelope<Record<string, unknown>>>(
        "API-155",
        `/api/v1/release-tasks/${taskId}/readiness`,
      ),
    enabled: Boolean(taskId),
  });

  const gate = readiness.data?.data ?? {};
  const overall = String(gate.overall ?? "");
  const gateItems = Array.isArray(gate.items) ? gate.items : [];
  const snapshot = asRecord(detailData.scope_snapshot ?? current?.scope_snapshot);
  const a5 = asRecord(detailData.a5);
  const divergence = asRecord(detailData.divergence);

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: queryKeys.releaseTasks({ projectId }) });
    void queryClient.invalidateQueries({ queryKey: ["release-tasks", taskId] });
  }

  const createMutation = useMutation({
    mutationFn: () =>
      api.post<ResourceEnvelope<Record<string, unknown>>>(
        "API-152",
        "/api/v1/release-tasks",
        { project_id: projectId, jira_version_ref: jiraVersionRef },
        newIdempotencyKey(),
      ),
    onMutate: () => setCommandError(null),
    onSuccess: (payload) => {
      invalidate();
      const id = String(payload.data.id ?? "");
      if (id) set({ id });
    },
    onError: (error) => setCommandError(error),
  });

  const pushMutation = useMutation({
    mutationFn: () =>
      api.post<ResourceEnvelope<Record<string, unknown>>>(
        "API-120",
        "/api/v1/action-previews",
        {
          action_type: "release_push",
          target_object_type: "release_task",
          target_object_id: taskId,
          project_id: projectId,
          payload: { confirm: true },
        },
        newIdempotencyKey(),
      ),
    onMutate: () => setCommandError(null),
    onSuccess: (payload) => {
      const approvalId = String(asRecord(payload.data).approval_request_id ?? "");
      if (approvalId) setPushPreviewId(approvalId);
    },
    onError: (error) => setCommandError(error),
  });

  const retryMutation = useMutation({
    mutationFn: () =>
      api.post(
        "API-153",
        `/api/v1/release-tasks/${taskId}/retries`,
        { expected_version: currentVersion },
        newIdempotencyKey(),
      ),
    onMutate: () => setCommandError(null),
    onSuccess: () => invalidate(),
    onError: (error) => setCommandError(error),
  });

  const cancelMutation = useMutation({
    mutationFn: () =>
      api.post(
        "API-154",
        `/api/v1/release-tasks/${taskId}/cancel`,
        { expected_version: currentVersion },
        newIdempotencyKey(),
      ),
    onMutate: () => setCommandError(null),
    onSuccess: () => {
      invalidate();
      setCancelOpen(false);
    },
    onError: (error) => setCommandError(error),
  });

  return (
    <>
      <PageHeader
        title="Release 任务"
        description="Jira 版本圈定 · 范围快照 · Readiness Gate · A5 草稿只读 · 审批后内部 prepare"
      />
      <Alert>
        <AlertDescription>
          无「执行生产发布」路径：平台只准备 release item。A5 草稿禁止自动推送。READY ≠ 生产已发布。
        </AlertDescription>
      </Alert>
      <CommandFeedback error={commandError} apis={PAGE_APIS.P17} action="Release 命令" />
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex flex-col gap-1">
          <Label htmlFor="release-project">项目 ID</Label>
          <Input
            id="release-project"
            className="w-72"
            value={projectId}
            onChange={(event) => set({ projectId: event.target.value, id: undefined })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="release-jira-version">Jira 版本号</Label>
          <Input
            id="release-jira-version"
            className="w-56"
            value={jiraVersionRef}
            onChange={(event) => set({ jiraVersionRef: event.target.value })}
            placeholder="v1.0"
          />
        </div>
        <MutateOnly>
          <Button
            onClick={() => createMutation.mutate()}
            disabled={createMutation.isPending || !projectId || !jiraVersionRef}
          >
            圈定版本创建（API-152）
          </Button>
        </MutateOnly>
      </div>
      {!projectId ? (
        <Alert>
          <AlertDescription>填写 projectId 后加载 Release 任务。</AlertDescription>
        </Alert>
      ) : (
        <QueryGate isPending={list.isPending} error={list.error} apis={PAGE_APIS.P17}>
          {items.length === 0 ? (
            <EmptyState title="无 Release 任务" />
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-[18rem_1fr]">
              <div className="flex flex-col gap-2">
                {items.map((item) => {
                  const id = String(item.id ?? "");
                  return (
                    <button
                      key={id}
                      type="button"
                      onClick={() => set({ id })}
                      className={cn("rounded-md border p-3 text-left", taskId === id ? "border-primary bg-accent" : "")}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-xs">{id.slice(0, 8)}</span>
                        <StatusBadge status={String(item.status ?? "")} />
                      </div>
                      <p className="text-sm">{String(item.jira_version_ref ?? "")}</p>
                    </button>
                  );
                })}
              </div>
              <div className="flex flex-col gap-4">
                <Card>
                  <CardHeader className="flex-row items-center justify-between">
                    <CardTitle>范围快照（创建后不可变）</CardTitle>
                    <div className="flex gap-2">
                      <MutateOnly>
                        {currentStatus === "PENDING_CONFIRM" ? (
                          <Button size="sm" onClick={() => setPushOpen(true)}>
                            发起 release_push 审批
                          </Button>
                        ) : null}
                        {RETRYABLE.has(currentStatus) ? (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => retryMutation.mutate()}
                            disabled={retryMutation.isPending}
                          >
                            幂等重试（API-153）
                          </Button>
                        ) : null}
                        {currentStatus === "PENDING_CONFIRM" || RETRYABLE.has(currentStatus) ? (
                          <Button size="sm" variant="destructive" onClick={() => setCancelOpen(true)}>
                            取消
                          </Button>
                        ) : null}
                      </MutateOnly>
                    </div>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-2">
                    <pre className="overflow-auto rounded-md bg-muted p-3 font-mono text-xs">
                      {JSON.stringify(snapshot, null, 2)}
                    </pre>
                    {pushPreviewId ? (
                      <p className="text-xs text-muted-foreground">
                        release_push 审批已创建（{pushPreviewId.slice(0, 8)}…），请到审批中心批准；批准后平台内部 prepare。
                      </p>
                    ) : null}
                    {divergence && Array.isArray(divergence.late_ready) && divergence.late_ready.length > 0 ? (
                      <Badge variant="destructive">迟到 READY 已记入 divergence（不覆盖取消）</Badge>
                    ) : null}
                  </CardContent>
                </Card>
                {readiness.error ? (
                  <Alert>
                    <AlertDescription>Readiness 暂不可用：{String(readiness.error)}</AlertDescription>
                  </Alert>
                ) : (
                  <Card>
                    <CardHeader>
                      <CardTitle>Readiness Gate</CardTitle>
                    </CardHeader>
                    <CardContent className="flex flex-col gap-2">
                      <div className="flex items-center gap-2">
                        <span className={cn("size-2.5 rounded-full", READINESS_TONE[overall] ?? "bg-muted")} />
                        <span className="text-sm font-medium">总体 {overall || "—"}</span>
                        <Badge variant="outline">红/黄/绿由后端评估</Badge>
                      </div>
                      {gateItems.map((item, index) => {
                        const row = asRecord(item);
                        const level = String(row.level ?? "");
                        return (
                          <div key={String(row.key ?? index)} className="flex items-center gap-3 rounded-md border p-3">
                            <span className={cn("size-2 rounded-full", READINESS_TONE[level] ?? "bg-muted")} />
                            <div className="flex-1">
                              <p className="text-sm">{String(row.key ?? "")}</p>
                              {row.unmet === true ? <p className="text-xs text-destructive">未满足</p> : null}
                            </div>
                          </div>
                        );
                      })}
                    </CardContent>
                  </Card>
                )}
                {a5 && Object.keys(a5).length > 0 ? (
                  <Card>
                    <CardHeader>
                      <CardTitle>A5 Release Notes 草稿（只读，禁止自动推送）</CardTitle>
                    </CardHeader>
                    <CardContent className="flex flex-col gap-2 text-sm">
                      <p>{String(a5.summary ?? "")}</p>
                      {Array.isArray(a5.missing_inputs) && a5.missing_inputs.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {a5.missing_inputs.map((input, index) => (
                            <Badge key={index} variant="outline">
                              缺失：{String(input)}
                            </Badge>
                          ))}
                        </div>
                      ) : null}
                      <pre className="overflow-auto rounded-md bg-muted p-3 font-mono text-xs">
                        {JSON.stringify(a5, null, 2)}
                      </pre>
                    </CardContent>
                  </Card>
                ) : null}
                {TERMINAL_READY.has(currentStatus) ? null : (
                  <Card>
                    <CardHeader>
                      <CardTitle>证据汇聚面板</CardTitle>
                    </CardHeader>
                    <CardContent className="text-sm text-muted-foreground">
                      计划执行结果、门禁结论、性能基线由服务端汇聚。前端不本地汇总当事实源。
                    </CardContent>
                  </Card>
                )}
              </div>
            </div>
          )}
        </QueryGate>
      )}
      <AlertDialog open={pushOpen} onOpenChange={setPushOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认推送到 Release 系统？</AlertDialogTitle>
            <AlertDialogDescription>
              发起 release_push Preview（L4 必审批）。审批通过后平台内部 prepare release item（幂等，不重复创建）。
              不提供执行生产发布 API。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={() => pushMutation.mutate()}>发起审批</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <AlertDialog open={cancelOpen} onOpenChange={setCancelOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>取消该 Release 任务？</AlertDialogTitle>
            <AlertDialogDescription>
              仅 PENDING_CONFIRM / FAILED_RETRYABLE 可取消。取消后迟到的 READY 只追加 divergence，不覆盖取消。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>返回</AlertDialogCancel>
            <AlertDialogAction onClick={() => cancelMutation.mutate()}>确认取消</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
