import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type {
  ActionPreview,
  CaseResultListItem,
  FailureClusterDetail,
  FailureClusterFixPreview,
  FailureClusterReport,
  ListEnvelope,
  ResourceEnvelope,
  TestRunCancelResult,
  TestRunDetail,
} from "@/api/types";
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
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [cancelOpen, setCancelOpen] = useState(false);
  const [signalSent, setSignalSent] = useState(false);
  const [cancelError, setCancelError] = useState<unknown>(null);
  const [healError, setHealError] = useState<unknown>(null);
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
      void queryClient.invalidateQueries({ queryKey: queryKeys.clusters(runId) });
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
      api.get<ResourceEnvelope<FailureClusterReport>>(
        "API-130",
        `/api/v1/test-runs/${runId}/failure-clusters`,
      ),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.data.generation_status;
      return status === "pending" ? 1000 : false;
    },
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
  const clusterReport = clusters.data?.data;
  const clusterItems = clusterReport?.items ?? [];
  const clusterIds = useMemo(() => clusterItems.map((item) => item.id), [clusterItems]);
  const clusterDetails = useQueries({
    queries: clusterIds.map((clusterId) => ({
      queryKey: ["failure-clusters", clusterId],
      queryFn: () =>
        api.get<ResourceEnvelope<FailureClusterDetail>>(
          "API-131",
          `/api/v1/failure-clusters/${clusterId}`,
        ),
      enabled: Boolean(clusterId),
    })),
  });
  const detailsById = useMemo(() => {
    const map = new Map<string, FailureClusterDetail>();
    clusterDetails.forEach((entry, index) => {
      const id = clusterIds[index];
      if (id && entry.data?.data) {
        map.set(id, entry.data.data);
      }
    });
    return map;
  }, [clusterDetails, clusterIds]);

  const resultItems = results.data?.data.items ?? [];
  const unclustered = clusterReport?.unclustered_refs ?? [];
  const degraded = clusterReport?.degraded === true;
  const firstResult = asRecord(resultItems[0]);
  const evidence = asRecord(firstResult.evidence);

  const healApply = useMutation({
    mutationFn: async (input: {
      clusterId: string;
      fix: FailureClusterFixPreview;
      testCaseId: string;
      caseVersion: number;
    }) => {
      const patch = parseSuggestedPatch(input.fix.suggested);
      return api.post<ResourceEnvelope<ActionPreview>>("API-120", "/api/v1/action-previews", {
        action_type: "heal_apply",
        project_id: run?.project_id,
        target_object_type: "test_case",
        target_object_id: input.testCaseId,
        expected_target_version: input.caseVersion,
        payload: {
          failure_cluster_id: input.clusterId,
          cluster_confidence: detailsById.get(input.clusterId)?.confidence,
          fix_confidence: input.fix.confidence,
          patch,
        },
      });
    },
    onMutate: () => setHealError(null),
    onSuccess: (payload) => {
      if (payload.data.gate === "REQUIRE_APPROVAL") {
        navigate("/approvals");
      }
    },
    onError: (error) => setHealError(error),
  });

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
            <AiDegradeBanner active={degraded} />
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
            {clusterItems.map((item) => {
              const detailRow = detailsById.get(item.id);
              const linkedCaseId = testCaseIdForCluster(item.failure_refs, resultItems);
              return (
                <ClusterCard
                  key={item.id}
                  cluster={{
                    id: item.id,
                    category: item.category,
                    confidence: item.confidence,
                    blocking: item.blocking_judgment,
                    summary: item.root_cause ?? undefined,
                    ruleFallback: degraded,
                    canShowApply: !degraded,
                    fixes: detailRow?.fixes_preview,
                  }}
                  applyPending={healApply.isPending}
                  onApply={(fix) => {
                    if (!linkedCaseId) {
                      setHealError(new Error("缺少目标用例"));
                      return;
                    }
                    void (async () => {
                      const caseDetail = await api.get<ResourceEnvelope<Record<string, unknown>>>(
                        "API-031",
                        `/api/v1/test-cases/${linkedCaseId}`,
                      );
                      const caseVersion = caseDetail.data.version;
                      if (typeof caseVersion !== "number") {
                        setHealError(new Error("缺少 expected_target_version"));
                        return;
                      }
                      healApply.mutate({
                        clusterId: item.id,
                        fix,
                        testCaseId: linkedCaseId,
                        caseVersion,
                      });
                    })();
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
                unclustered.map((caseResultId) => (
                  <Link
                    key={caseResultId}
                    className="mb-1 block font-mono text-xs text-primary underline"
                    to={`/test-center/case-results/${caseResultId}`}
                  >
                    {caseResultId}
                  </Link>
                ))
              )}
            </div>
            <CommandFeedback error={healError} apis={PAGE_APIS.P09} action="heal_apply Preview（API-120）" />
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
                  {resultItems.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell className="font-mono text-xs">{item.test_case_id}</TableCell>
                      <TableCell>
                        <StatusBadge status={item.outcome} />
                      </TableCell>
                    </TableRow>
                  ))}
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

function testCaseIdForCluster(
  failureRefs: string[],
  resultItems: CaseResultListItem[],
): string | undefined {
  const ref = failureRefs[0];
  if (ref) {
    const match = resultItems.find((row) => row.id === ref);
    if (match?.test_case_id) {
      return match.test_case_id;
    }
  }
  return resultItems[0]?.test_case_id;
}

function parseSuggestedPatch(suggested: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(suggested) as unknown;
    if (typeof parsed === "object" && parsed !== null) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return { assertions: [{ type: "status_code", expected: Number(suggested) || 200 }] };
  }
  return {};
}

function StepMark({ step }: { step: string }) {
  return (
    <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-secondary font-mono text-xs font-semibold text-secondary-foreground">
      {step}
    </span>
  );
}
