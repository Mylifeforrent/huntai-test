import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ListEnvelope, ResourceEnvelope } from "@/api/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
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
import { StatusBadge } from "@/components/domain/StatusBadge";
import { UndevelopedCallout } from "@/components/domain/UndevelopedCallout";
import { useUrlState } from "@/hooks/useUrlState";
import { cn } from "@/lib/utils";

const READINESS_TONE: Record<string, string> = {
  green: "bg-success",
  yellow: "bg-warning",
  red: "bg-destructive",
  pass: "bg-success",
  warn: "bg-warning",
  fail: "bg-destructive",
};

export function ReleaseTaskPage() {
  const { get, set } = useUrlState();
  const projectId = get("projectId");
  const selectedId = get("id");
  const [pushOpen, setPushOpen] = useState(false);
  const [pushTried, setPushTried] = useState(false);

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
  const snapshot = asRecord(current?.scope_snapshot);

  function previewPush() {
    setPushTried(true);
    void api
      .post("API-120", "/api/v1/action-previews", {
        action_type: "release_push",
        target_object_type: "release_task",
        target_object_id: taskId,
        payload: {},
      })
      .catch(() => undefined);
  }

  return (
    <>
      <PageHeader
        title="Release 任务"
        description="范围快照 · 证据汇聚面板 · Readiness Gate 红黄绿 · 推送预览+确认。M3。"
      />
      <Input
        placeholder="projectId（API-150 必填）"
        value={projectId}
        onChange={(event) => set({ projectId: event.target.value })}
        className="max-w-72"
      />
      {!projectId ? (
        <Alert>
          <AlertDescription>填写 projectId 后加载 Release 任务。无「执行生产发布」路径。</AlertDescription>
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
                        <span className="font-mono text-xs">{id}</span>
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
                    <CardTitle>范围快照</CardTitle>
                    <Button size="sm" onClick={() => setPushOpen(true)}>
                      推送预览
                    </Button>
                  </CardHeader>
                  <CardContent>
                    <pre className="overflow-auto rounded-md bg-muted p-3 font-mono text-xs">
                      {JSON.stringify(snapshot, null, 2)}
                    </pre>
                    <p className="mt-2 text-xs text-muted-foreground">创建后不可变。READY ≠ 生产已发布。</p>
                  </CardContent>
                </Card>
                {readiness.error ? (
                  <UndevelopedCallout apis={PAGE_APIS.P17} error={readiness.error} action="Readiness Gate" />
                ) : (
                  <Card>
                    <CardHeader>
                      <CardTitle>Readiness Gate</CardTitle>
                    </CardHeader>
                    <CardContent className="flex flex-col gap-2">
                      <div className="flex items-center gap-2">
                        <span className={cn("size-2.5 rounded-full", READINESS_TONE[overall] ?? "bg-muted")} />
                        <span className="text-sm font-medium">总体 {overall || "—"}</span>
                        <Badge variant="outline">红 / 黄 / 绿 由后端评估</Badge>
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
                <Card>
                  <CardHeader>
                    <CardTitle>证据汇聚面板</CardTitle>
                  </CardHeader>
                  <CardContent className="text-sm text-muted-foreground">
                    计划执行结果、门禁结论、性能基线由服务端汇聚。前端不本地汇总当事实源。
                  </CardContent>
                </Card>
              </div>
            </div>
          )}
        </QueryGate>
      )}
      {pushTried ? <UndevelopedCallout apis={PAGE_APIS.P17} action="release_push Preview（API-120）" /> : null}
      <AlertDialog open={pushOpen} onOpenChange={setPushOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认推送到 Release 系统？</AlertDialogTitle>
            <AlertDialogDescription>
              发起 release_push Preview（L4）。审批通过后平台调用 Release 系统准备 release item。不提供执行生产发布 API。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={previewPush}>发起预览</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}
