import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type {
  ActionPreview,
  ArtifactMetadata,
  CaseResultDetail,
  CaseResultListItem,
  FailureClusterDetail,
  FailureClusterFixPreview,
  FailureClusterReport,
  ListEnvelope,
  ResourceEnvelope,
  SimilarFailureClusterItem,
  StepRunItem,
  TestRunCancelResult,
  TestRunDetail,
} from "@/api/types";
import { TEST_RUN_TERMINALS } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CommandFeedback, PageHeader, QueryGate, EmptyState, StepMark } from "@/components/domain/PageState";
import { RunProgressBar } from "@/components/domain/RunProgressBar";
import { ClusterCard } from "@/components/domain/ClusterCard";
import { EvidenceViewer } from "@/components/domain/EvidenceViewer";
import { AiDegradeBanner } from "@/components/domain/AiDegradeBanner";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { useSession } from "@/hooks/useSession";
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
export function TestRunDetailPage() {
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const session = useSession();
  const [cancelOpen, setCancelOpen] = useState(false);
  const [signalSent, setSignalSent] = useState(false);
  const [cancelError, setCancelError] = useState<unknown>(null);
  const [healError, setHealError] = useState<unknown>(null);
  const [jiraError, setJiraError] = useState<unknown>(null);
  const [correctError, setCorrectError] = useState<unknown>(null);
  const [sseHint, setSseHint] = useState<string | null>(null);
  const [selectedCaseResultId, setSelectedCaseResultId] = useState<string | null>(null);

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
  const projectRole = session.me?.memberships?.find((item) => item.project_id === run?.project_id)?.role;
  const canCreateJira = status === "FAILED" && projectRole !== "viewer";
  const source = run?.execution_source;
  const version = run?.version;
  const clusterReport = clusters.data?.data;
  const clusterItems = clusterReport?.items ?? [];
  const clusterPending = clusterReport?.generation_status === "pending";
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
  const similarQueries = useQueries({
    queries: clusterIds.map((clusterId) => ({
      queryKey: ["failure-clusters", clusterId, "similar"],
      queryFn: () =>
        api.get<ListEnvelope<SimilarFailureClusterItem>>(
          "API-133",
          `/api/v1/failure-clusters/${clusterId}/similar`,
        ),
      enabled: Boolean(clusterId) && !clusterPending,
    })),
  });
  const similarById = useMemo(() => {
    const map = new Map<string, SimilarFailureClusterItem[]>();
    similarQueries.forEach((entry, index) => {
      const id = clusterIds[index];
      if (id && entry.data?.data.items) {
        map.set(id, entry.data.data.items);
      }
    });
    return map;
  }, [similarQueries, clusterIds]);

  const resultItems = results.data?.data.items ?? [];
  const unclustered = clusterReport?.unclustered_refs ?? [];
  const degraded = clusterReport?.degraded === true;

  useEffect(() => {
    if (resultItems.length === 0) {
      setSelectedCaseResultId(null);
      return;
    }
    setSelectedCaseResultId((current) => {
      if (current && resultItems.some((item) => item.id === current)) {
        return current;
      }
      const failed = resultItems.find((item) => item.outcome === "failed");
      return failed?.id ?? resultItems[0]?.id ?? null;
    });
  }, [resultItems]);

  const caseResultDetail = useQuery({
    queryKey: ["case-results", selectedCaseResultId],
    queryFn: () =>
      api.get<ResourceEnvelope<CaseResultDetail>>(
        "API-065",
        `/api/v1/case-results/${selectedCaseResultId}`,
      ),
    enabled: Boolean(selectedCaseResultId),
  });
  const stepRuns = useQuery({
    queryKey: ["case-results", selectedCaseResultId, "step-runs"],
    queryFn: () =>
      api.get<ListEnvelope<StepRunItem>>(
        "API-066",
        `/api/v1/case-results/${selectedCaseResultId}/step-runs`,
      ),
    enabled: Boolean(selectedCaseResultId),
  });

  const artifactMetaQueries = useQueries({
    queries: (caseResultDetail.data?.data.artifact_ids ?? []).map((artifactId) => ({
      queryKey: ["artifacts", artifactId],
      queryFn: () =>
        api.get<ResourceEnvelope<ArtifactMetadata>>("API-220", `/api/v1/artifacts/${artifactId}`),
      enabled: Boolean(artifactId),
    })),
  });
  const artifactsByKind = useMemo(() => {
    const map = new Map<string, string>();
    artifactMetaQueries.forEach((entry) => {
      const kind = entry.data?.data.kind;
      const id = entry.data?.data.id;
      if (kind && id) map.set(kind, id);
    });
    return map;
  }, [artifactMetaQueries]);

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

  const jiraWrite = useMutation({
    mutationFn: async (input: {
      clusterId: string;
      description: string;
      reproSteps: string;
      evidenceIds: string[];
      jiraProject?: string;
    }) => {
      return api.post<ResourceEnvelope<ActionPreview>>("API-120", "/api/v1/action-previews", {
        action_type: "jira_write",
        project_id: run?.project_id,
        target_object_type: "failure_cluster",
        target_object_id: input.clusterId,
        payload: {
          description: input.description,
          repro_steps: input.reproSteps,
          jira_project: input.jiraProject,
          evidence_ids: input.evidenceIds,
        },
      });
    },
    onMutate: () => setJiraError(null),
    onSuccess: (payload) => {
      if (payload.data.gate === "REQUIRE_APPROVAL" && payload.data.approval_request_id) {
        navigate(`/approvals?highlight=${payload.data.approval_request_id}`);
      }
    },
    onError: (error) => setJiraError(error),
  });

  const correctCluster = useMutation({
    mutationFn: async (input: {
      clusterId: string;
      category: string;
      blocking: string;
      currentCategory: string;
      currentBlocking: string;
    }) => {
      const corrections: Array<{
        field: string;
        old?: string;
        new: string;
      }> = [];
      if (input.category.trim()) {
        corrections.push({
          field: "category",
          old: input.currentCategory,
          new: input.category.trim(),
        });
      }
      if (input.blocking.trim()) {
        corrections.push({
          field: "blocking_judgment",
          old: input.currentBlocking,
          new: input.blocking.trim(),
        });
      }
      if (corrections.length === 0) {
        throw new Error("请填写至少一项修正");
      }
      return api.patch<ResourceEnvelope<FailureClusterDetail>>(
        "API-132",
        `/api/v1/failure-clusters/${input.clusterId}`,
        { corrections },
      );
    },
    onMutate: () => setCorrectError(null),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.clusters(runId) });
      void queryClient.invalidateQueries({ queryKey: ["failure-clusters"] });
    },
    onError: (error) => setCorrectError(error),
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
            {run?.execution_source_badge?.normalized_from_external_ci ? (
              <StatusBadge status="external_ci" />
            ) : null}
            {typeof run?.result_summary?.ci === "object" &&
            run.result_summary.ci !== null &&
            typeof (run.result_summary.ci as Record<string, unknown>).report_parse === "object" ? (
              <p className="text-xs text-muted-foreground">
                报告解析进度：{" "}
                {JSON.stringify((run.result_summary.ci as Record<string, unknown>).report_parse)}
              </p>
            ) : null}
            {typeof run?.result_summary?.ci === "object" &&
            run.result_summary.ci !== null &&
            (run.result_summary.ci as Record<string, unknown>).reason ? (
              <p className="text-xs text-destructive">
                CI 采集失败：{String((run.result_summary.ci as Record<string, unknown>).reason)}
              </p>
            ) : null}
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
            {clusterPending ? (
              <p className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">
                聚类生成中 — 权威报告以 API-130 为准，SSE 进度不代表报告就绪。
              </p>
            ) : null}
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
                    evidenceRefs: item.evidence_refs,
                    failureRefs: item.failure_refs,
                    jiraIssue: detailRow?.jira_issue ?? item.jira_issue,
                    correctionHistory: detailRow?.correction_history,
                    similarItems: similarById.get(item.id),
                  }}
                  correctPending={correctCluster.isPending}
                  onCorrect={({ category, blocking }) => {
                    correctCluster.mutate({
                      clusterId: item.id,
                      category,
                      blocking,
                      currentCategory: item.category,
                      currentBlocking: item.blocking_judgment,
                    });
                  }}
                  applyPending={healApply.isPending}
                  jiraPending={jiraWrite.isPending}
                  showJiraButton={canCreateJira && !item.jira_issue && !detailRow?.jira_issue}
                  onCreateJira={() => {
                    jiraWrite.mutate({
                      clusterId: item.id,
                      description: item.root_cause ?? "失败聚类缺陷",
                      reproSteps: `TestRun ${runId} · cluster ${item.id}`,
                      evidenceIds: item.evidence_refs ?? [],
                    });
                  }}
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
            <CommandFeedback error={jiraError} apis={PAGE_APIS.P09} action="jira_write Preview（API-120）" />
            <CommandFeedback error={correctError} apis={PAGE_APIS.P09} action="人工修正（API-132）" />
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
                    <TableHead>Partial</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {resultItems.map((item) => (
                    <TableRow
                      key={item.id}
                      className={
                        item.id === selectedCaseResultId ? "cursor-pointer bg-muted/50" : "cursor-pointer"
                      }
                      onClick={() => setSelectedCaseResultId(item.id)}
                    >
                      <TableCell className="font-mono text-xs">{item.test_case_id}</TableCell>
                      <TableCell>
                        <StatusBadge status={item.outcome} />
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {item.is_partial ? "partial" : "—"}
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
            {!selectedCaseResultId ? (
              <EmptyState compact title="未选用例结果" hint="点击上方结果行查看证据" />
            ) : (
              <EvidenceViewer
                screenshotArtifactId={artifactsByKind.get("screenshot")}
                videoArtifactId={artifactsByKind.get("video")}
                traceArtifactId={artifactsByKind.get("trace")}
                stepRuns={stepRuns.data?.data.items ?? []}
              />
            )}
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
