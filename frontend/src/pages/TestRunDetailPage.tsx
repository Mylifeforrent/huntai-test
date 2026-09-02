import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { CaseResultListItem, ListEnvelope, ResourceEnvelope, TestRunCancelResult, TestRunDetail } from "@/api/types";
import { TEST_RUN_TERMINALS } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CommandFeedback, PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { RunProgressBar } from "@/components/domain/RunProgressBar";
import { ClusterCard } from "@/components/domain/ClusterCard";
import { EvidenceViewer } from "@/components/domain/EvidenceViewer";
import { AiDegradeBanner } from "@/components/domain/AiDegradeBanner";
import { StatusBadge } from "@/components/domain/StatusBadge";
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
import { asRecord } from "@/lib/utils";

export function TestRunDetailPage() {
  const { runId = "" } = useParams();
  const queryClient = useQueryClient();
  const [cancelOpen, setCancelOpen] = useState(false);
  const [signalSent, setSignalSent] = useState(false);
  const [cancelError, setCancelError] = useState<unknown>(null);
  const [sseHint, setSseHint] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) {
      return undefined;
    }
    const source = new EventSource(`/api/v1/test-runs/${runId}/events`, { withCredentials: true });
    const onProgress = (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as { hint?: string };
        setSseHint(payload.hint ?? "progress");
      } catch {
        setSseHint("progress");
      }
    };
    const onChanged = () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.testRun(runId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.caseResults(runId) });
    };
    source.addEventListener("progress", onProgress);
    source.addEventListener("resource_changed", onChanged);
    return () => {
      source.removeEventListener("progress", onProgress);
      source.removeEventListener("resource_changed", onChanged);
      source.close();
    };
  }, [queryClient, runId]);

  const detail = useQuery({
    queryKey: queryKeys.testRun(runId),
    queryFn: () => api.get<ResourceEnvelope<TestRunDetail>>("API-061", `/api/v1/test-runs/${runId}`),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      const current = query.state.data?.data.status;
      if (current && (TEST_RUN_TERMINALS as readonly string[]).includes(current)) {
        return false;
      }
      return 1000;
    },
  });
  const clusters = useQuery({
    queryKey: queryKeys.clusters(runId),
    queryFn: () =>
      api.get<ListEnvelope<Record<string, unknown>>>("API-130", `/api/v1/test-runs/${runId}/failure-clusters`),
    enabled: Boolean(runId),
  });
  const results = useQuery({
    queryKey: queryKeys.caseResults(runId),
    queryFn: () =>
      api.get<ListEnvelope<CaseResultListItem>>("API-064", `/api/v1/test-runs/${runId}/case-results`),
    enabled: Boolean(runId),
  });

  const run = detail.data?.data;
  const status = run?.status ?? "";
  const source = run?.execution_source;
  const version = run?.version;
  const clusterItems = clusters.data?.data.items ?? [];
  const resultItems = results.data?.data.items ?? [];
  const unclustered = Array.isArray(asRecord(clusters.data?.data).unclustered_refs)
    ? (asRecord(clusters.data?.data).unclustered_refs as unknown[])
    : [];
  const firstResult = asRecord(resultItems[0]);
  const evidence = asRecord(firstResult.evidence);

  const cancel = useMutation({
    mutationFn: () => {
      if (typeof version !== "number") {
        throw new Error("缺少 expected_version，无法提交终止");
      }
      return api.post<ResourceEnvelope<TestRunCancelResult>>(
        "API-063",
        `/api/v1/test-runs/${runId}/cancel`,
        { expected_version: version },
      );
    },
    onMutate: () => setCancelError(null),
    onSuccess: (payload) => {
      const cancelledRun = payload.data.test_run;
      if (cancelledRun.status === "CANCELLED") {
        setSignalSent(true);
      } else if (cancelledRun.status === "STOPPING" || cancelledRun.stop_signal_at) {
        setSignalSent(true);
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.testRun(runId) });
    },
    onError: (error) => setCancelError(error),
  });

  return (
    <>
      <PageHeader
        title={`TestRun ${runId || ""}`}
        description="页头进度条 → 聚类报告 → 用例结果 → 证据查看器"
        actions={
          <div className="flex gap-2">
            {source === "agent" ? (
              <Button variant="outline" asChild>
                <Link to={`/test-center/runs/${runId}/agent`}>Agent 轨迹</Link>
              </Button>
            ) : null}
            <Button variant="destructive" onClick={() => setCancelOpen(true)}>
              终止
            </Button>
          </div>
        }
      />
      <QueryGate isPending={detail.isPending} error={detail.error} apis={PAGE_APIS.P09}>
        <Card>
          <CardHeader className="flex-row items-start gap-3">
            <StepMark step="1" />
            <div className="flex min-w-0 flex-col gap-1">
              <CardTitle>执行进度</CardTitle>
              <CardDescription>状态由服务端下发，前端不推演迁移</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <RunProgressBar status={status} source={source} />
            {sseHint ? (
              <p className="text-xs text-muted-foreground">SSE 提示（非终态）：{sseHint}。权威状态以 GET API-061 为准。</p>
            ) : null}
            {status === "WAITING_APPROVAL" ? (
              <Button variant="outline" asChild className="w-fit">
                <Link to="/approvals">WAITING_APPROVAL · 前往审批中心</Link>
              </Button>
            ) : null}
            {signalSent ? (
              <p className="text-sm text-success">
                终止信号已持久化送达。
                {status === "STOPPING" ? " STOPPING → CANCELLED 由服务端推进。" : ""}
                {status === "CANCELLED" ? "" : " 当前状态不等于 CANCELLED。"}
              </p>
            ) : null}
            {run?.stop_signal_at && status !== "CANCELLED" ? (
              <p className="text-xs text-muted-foreground">
                stop_signal_at 已设置（{run.stop_signal_at}），不等于 CANCELLED。
              </p>
            ) : null}
            <AiDegradeBanner active={false} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex-row items-start gap-3">
            <StepMark step="2" />
            <div className="flex min-w-0 flex-col gap-1">
              <CardTitle>聚类报告区</CardTitle>
              <CardDescription>失败归因簇；无法判断项须逐条可点开</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {clusters.error ? (
              <CommandFeedback error={clusters.error} apis={PAGE_APIS.P09} action="失败聚类" />
            ) : null}
            {!clusters.error && clusterItems.length === 0 ? (
              <EmptyState compact title="无聚类报告" hint="空集是服务端下发；运行中或无失败时可能为空。" />
            ) : null}
            {clusterItems.map((item, index) => {
              const row = asRecord(item);
              return (
                <ClusterCard
                  key={String(row.id ?? index)}
                  cluster={{
                    id: String(row.id ?? index),
                    category: String(row.category ?? "unknown"),
                    confidence: typeof row.confidence === "number" ? row.confidence : 0,
                    blocking: String(row.blocking_judgment ?? "uncertain"),
                    summary: typeof row.summary === "string" ? row.summary : undefined,
                    ruleFallback: row.result === "degraded",
                    canShowApply: Number(row.confidence ?? 0) >= 0.7,
                    evidenceHref: typeof row.evidence_href === "string" ? row.evidence_href : undefined,
                  }}
                />
              );
            })}
            <div className="rounded-md border border-dashed bg-muted/40 p-3 text-xs text-muted-foreground">
              <p className="mb-2 font-medium text-foreground">无法判断项（unclustered_refs）</p>
              {clusters.error ? (
                <p>聚类查询失败时不把失败当成空的无法判断项。</p>
              ) : unclustered.length === 0 ? (
                <p>服务端未返回无法判断项。</p>
              ) : (
                unclustered.map((item: unknown, index: number) => {
                  const row = asRecord(item);
                  const id = String(row.id ?? row.case_result_id ?? index);
                  return (
                    <details key={id} className="mb-1">
                      <summary className="cursor-pointer font-mono text-xs text-primary">{id}</summary>
                      <pre className="mt-1 overflow-auto rounded bg-muted p-2 text-[10px]">
                        {JSON.stringify(item, null, 2)}
                      </pre>
                    </details>
                  );
                })
              )}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex-row items-start gap-3">
            <StepMark step="3" />
            <div className="flex min-w-0 flex-col gap-1">
              <CardTitle>用例结果表</CardTitle>
              <CardDescription>逐步结果，不含前端推演</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {results.error ? (
              <CommandFeedback error={results.error} apis={PAGE_APIS.P09} action="用例结果" />
            ) : null}
            {!results.error && resultItems.length === 0 ? (
              <EmptyState compact title="无用例结果" hint="空集是 200 + items: []。" />
            ) : null}
            {resultItems.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Case</TableHead>
                    <TableHead>结果</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {resultItems.map((item, index) => {
                    const row = asRecord(item);
                    return (
                      <TableRow key={String(row.id ?? index)}>
                        <TableCell className="font-mono text-xs">{String(row.test_case_id ?? row.id ?? "")}</TableCell>
                        <TableCell>
                          <StatusBadge status={String(row.outcome ?? "")} />
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex-row items-start gap-3">
            <StepMark step="4" />
            <div className="flex min-w-0 flex-col gap-1">
              <CardTitle>证据查看器</CardTitle>
              <CardDescription>截图 / 视频 / Trace，制品由后端代理</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <EvidenceViewer
              screenshotUrl={typeof evidence.screenshot_url === "string" ? evidence.screenshot_url : undefined}
              videoUrl={typeof evidence.video_url === "string" ? evidence.video_url : undefined}
              traceAvailable={evidence.trace_available === true}
            />
            {source ? <StatusBadge status={source} /> : null}
          </CardContent>
        </Card>
      </QueryGate>
      <CommandFeedback error={cancelError} apis={PAGE_APIS.P09} action="终止 TestRun（API-063）" />
      <AlertDialog open={cancelOpen} onOpenChange={setCancelOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认终止？</AlertDialogTitle>
            <AlertDialogDescription>终止信号由服务端持久化。前端只展示「已送达」，不把 run 标为 CANCELLED。</AlertDialogDescription>
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
    </>
  );
}

function StepMark({ step }: { step: string }) {
  return (
    <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-secondary font-mono text-xs font-semibold text-secondary-foreground">
      {step}
    </span>
  );
}
