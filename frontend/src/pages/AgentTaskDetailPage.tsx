import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ResourceEnvelope } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { StatusBadge } from "@/components/domain/StatusBadge";
import { asRecord } from "@/lib/utils";

export function AgentTaskDetailPage() {
  const { runId = "" } = useParams();
  const queryClient = useQueryClient();
  const [cancelOpen, setCancelOpen] = useState(false);
  const [draftOpen, setDraftOpen] = useState(false);
  const [cancelError, setCancelError] = useState<unknown>(null);
  const [draftError, setDraftError] = useState<unknown>(null);
  const [signalSent, setSignalSent] = useState(false);

  const query = useQuery({
    queryKey: queryKeys.trajectory(runId),
    queryFn: () =>
      api.get<ResourceEnvelope<Record<string, unknown>>>("API-067", `/api/v1/test-runs/${runId}/trajectory`),
    enabled: Boolean(runId),
  });
  const runQuery = useQuery({
    queryKey: queryKeys.testRun(runId),
    queryFn: () => api.get<ResourceEnvelope<Record<string, unknown>>>("API-061", `/api/v1/test-runs/${runId}`),
    enabled: Boolean(runId),
  });

  const data = query.data?.data ?? {};
  const a8 = asRecord(data.a8);
  const steps = Array.isArray(a8.steps) ? a8.steps : [];
  const incomplete = a8.incomplete === true || a8.status === "incomplete";
  const tokenUsage = asRecord(a8.token_usage);
  const version = typeof runQuery.data?.data.version === "number" ? runQuery.data.data.version : undefined;

  const cancel = useMutation({
    mutationFn: () => {
      if (typeof version !== "number") {
        throw new Error("缺少 expected_version，无法提交终止");
      }
      return api.post("API-063", `/api/v1/test-runs/${runId}/cancel`, { expected_version: version });
    },
    onMutate: () => setCancelError(null),
    onSuccess: () => {
      setSignalSent(true);
      void queryClient.invalidateQueries({ queryKey: queryKeys.trajectory(runId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.testRun(runId) });
    },
    onError: (error) => setCancelError(error),
  });

  const draft = useMutation({
    mutationFn: () => api.post("API-068", `/api/v1/test-runs/${runId}/script-drafts`, {}),
    onMutate: () => setDraftError(null),
    onError: (error) => setDraftError(error),
  });

  return (
    <>
      <PageHeader
        title={`Agent 任务 ${runId}`}
        description="轨迹时间线（每步动作+截图+工具调用）· 终止（持久化信号）· 转脚本草稿 · incomplete 标记"
        actions={
          <div className="flex gap-2">
            <Button variant="destructive" onClick={() => setCancelOpen(true)}>
              终止
            </Button>
            <Button variant="outline" onClick={() => setDraftOpen(true)}>
              转脚本草稿
            </Button>
          </div>
        }
      />
      <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P14}>
        {data.available === false ? (
          <EmptyState title="无 Agent 轨迹" hint={String(data.unavailable_reason ?? "非 agent 来源不发明新状态")} />
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status="agent" />
              <Badge variant="secondary">不进门禁</Badge>
              {incomplete ? <Badge variant="warning">incomplete</Badge> : null}
              {signalSent ? <p className="text-sm text-success">终止信号已持久化送达。</p> : null}
              <StatusBadge status={String(a8.status ?? "")} />
              <span className="font-mono text-xs text-muted-foreground">
                token_usage {String(tokenUsage.total ?? tokenUsage.prompt ?? "—")}
              </span>
            </div>
            <Card>
              <CardHeader>
                <CardTitle>执行轨迹</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                {steps.length === 0 ? <EmptyState title="无步骤" /> : null}
                {steps.map((item, index) => {
                  const row = asRecord(item);
                  const action = asRecord(row.action);
                  return (
                    <div key={String(row.seq ?? index)} className="flex gap-3 rounded-md border p-3">
                      <div className="flex size-7 items-center justify-center rounded-full bg-muted font-mono text-xs">
                        {String(row.seq ?? index + 1)}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium">{String(row.intent ?? "步骤")}</p>
                        <p className="font-mono text-xs text-muted-foreground">
                          {String(action.tool ?? "")} · hash {String(action.args_hash ?? "—")}
                        </p>
                        {row.screenshot_ref ? <Badge variant="outline">截图</Badge> : null}
                        <p className="font-mono text-xs text-muted-foreground">{String(row.elapsed_ms ?? "")} ms</p>
                      </div>
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          </>
        )}
      </QueryGate>
      <CommandFeedback error={cancelError} apis={PAGE_APIS.P14} action="终止信号 API-063" />
      <CommandFeedback error={draftError} apis={PAGE_APIS.P14} action="转脚本草稿 API-068" />
      <AlertDialog open={cancelOpen} onOpenChange={setCancelOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认终止 Agent 任务？</AlertDialogTitle>
            <AlertDialogDescription>
              发送持久化终止信号。已产生的轨迹照常保存。Agent 任务无自动重试。前端不把 run 标为 CANCELLED。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                cancel.mutate();
              }}
            >
              发送终止
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <AlertDialog open={draftOpen} onOpenChange={setDraftOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>转换为 Script 草稿？</AlertDialogTitle>
            <AlertDialogDescription>
              成功轨迹转为 Script Mode 草稿。过 schema 后须人工确认并经 DRAFT→PENDING_REVIEW→ACTIVE 评审流入库。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                draft.mutate();
              }}
            >
              确认转换
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

