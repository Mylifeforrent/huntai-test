import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { newIdempotencyKey } from "@/api/apiConfig";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ListEnvelope, ResourceEnvelope } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
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
import { useUrlState } from "@/hooks/useUrlState";

const KILL_SWITCH_MODULE = "performance";

export function PerformancePage() {
  const queryClient = useQueryClient();
  const { get, set } = useUrlState();
  const projectId = get("projectId");
  const scenarioId = get("scenarioId");
  const targetEnv = get("targetEnv");
  const whitelist = get("whitelist");
  const users = get("users");
  const runTime = get("runTime");
  const [killOpen, setKillOpen] = useState(false);
  const [commandError, setCommandError] = useState<unknown>(null);
  const [startedRunId, setStartedRunId] = useState<string | null>(null);
  const [startHint, setStartHint] = useState<string | null>(null);

  const org = useQuery({
    queryKey: queryKeys.organization,
    queryFn: () => api.get("API-010", "/api/v1/organizations/current"),
  });

  const query = useQuery({
    queryKey: ["perf-baselines", scenarioId],
    queryFn: () =>
      api.get<ListEnvelope<Record<string, unknown>>>("API-056", "/api/v1/perf-baselines", {
        scenario_test_case_id: scenarioId,
      }),
    enabled: Boolean(scenarioId),
  });
  const items = query.data?.data.items ?? [];
  const orgVersion = (org.data as { data?: { version?: number } } | undefined)?.data?.version;

  const tightenMutation = useMutation({
    mutationFn: () =>
      api.post("API-199", "/api/v1/organizations/current/capability-controls/tighten", {
        expected_version: orgVersion,
        target: { level: "module", module: KILL_SWITCH_MODULE },
        reason: "performance kill switch drill",
      }),
    onMutate: () => setCommandError(null),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.organization });
      void queryClient.invalidateQueries({ queryKey: queryKeys.me });
    },
    onError: (error) => setCommandError(error),
  });

  const startMutation = useMutation({
    mutationFn: () =>
      api.post<ResourceEnvelope<Record<string, unknown>>>(
        "API-062",
        "/api/v1/test-runs",
        {
          project_id: projectId,
          env_id: get("envId"),
          execution_source: "script",
          case_ids: [scenarioId],
          trigger_type: "manual",
          params: {
            TARGET_ENV: targetEnv,
            perf_whitelist: whitelist
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean),
            perf_scenario: {
              users: Number(users) || 1,
              run_time_seconds: Number(runTime) || 60,
            },
          },
        },
        newIdempotencyKey(),
      ),
    onMutate: () => {
      setCommandError(null);
      setStartHint(null);
    },
    onSuccess: (payload) => {
      const runId = String(payload.data.id ?? "");
      setStartedRunId(runId);
      const summary = payload.data.result_summary;
      if (summary && typeof summary === "object" && "queued" in summary) {
        setStartHint("同场景已有在途施压：本次受理已排队（不并行施压）。");
      }
    },
    onError: (error) => setCommandError(error),
  });

  const baselineMutation = useMutation({
    mutationFn: () =>
      api.post<ResourceEnvelope<Record<string, unknown>>>(
        "API-057",
        "/api/v1/perf-baselines",
        {
          scenario_test_case_id: scenarioId,
          metrics_snapshot: { p95_ms: Number(get("baselineP95")) || 0 },
          tolerance: { rt: Number(get("baselineTolerance")) || 0.2 },
        },
        newIdempotencyKey(),
      ),
    onMutate: () => setCommandError(null),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["perf-baselines", scenarioId] });
    },
    onError: (error) => setCommandError(error),
  });

  function tighten() {
    setKillOpen(false);
    tightenMutation.mutate();
  }

  return (
    <>
      <PageHeader
        title="性能压测"
        description="场景发起（白名单环境）· 基线对比 · kill switch · 压力机自监控"
      />
      <Alert>
        <AlertTitle>无自动重试</AlertTitle>
        <AlertDescription>
          压测任务失败或 kill switch 关停后严禁自动重试。白名单外目标直接拒绝（HT-POL-002），不进审批。
          L2+ 高危配置会自动创建 perf_high_risk 审批，批准后继续施压。
        </AlertDescription>
      </Alert>
      <CommandFeedback error={commandError} apis={PAGE_APIS.P16} action="压测命令" />
      <div className="flex flex-wrap items-end gap-2">
        <Button variant="destructive" onClick={() => setKillOpen(true)} disabled={orgVersion === undefined}>
          Kill switch 关停压测模块
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>发起压测（统一 TestRun）</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2">
          <div className="flex flex-col gap-1">
            <Label htmlFor="perf-project">项目 ID</Label>
            <Input
              id="perf-project"
              value={projectId}
              onChange={(event) => set({ projectId: event.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="perf-env">环境 ID</Label>
            <Input id="perf-env" value={get("envId")} onChange={(event) => set({ envId: event.target.value })} />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="perf-scenario">场景用例 ID（case_type=performance）</Label>
            <Input
              id="perf-scenario"
              value={scenarioId}
              onChange={(event) => set({ scenarioId: event.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="perf-target">目标地址（TARGET_ENV）</Label>
            <Input
              id="perf-target"
              value={targetEnv}
              onChange={(event) => set({ targetEnv: event.target.value })}
              placeholder="http://target.example"
            />
          </div>
          <div className="flex flex-col gap-1 md:col-span-2">
            <Label htmlFor="perf-whitelist">目标白名单（逗号分隔前缀）</Label>
            <Input
              id="perf-whitelist"
              value={whitelist}
              onChange={(event) => set({ whitelist: event.target.value })}
              placeholder="http://target.example,http://staging.internal"
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="perf-users">并发用户数</Label>
            <Input
              id="perf-users"
              value={users}
              onChange={(event) => set({ users: event.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="perf-runtime">施压时长（秒）</Label>
            <Input
              id="perf-runtime"
              value={runTime}
              onChange={(event) => set({ runTime: event.target.value })}
            />
          </div>
          <div className="flex items-center gap-3 md:col-span-2">
            <Button
              onClick={() => startMutation.mutate()}
              disabled={
                startMutation.isPending || !projectId || !get("envId") || !scenarioId || !targetEnv
              }
            >
              发起压测
            </Button>
            {startedRunId ? (
              <Link className="text-sm text-primary underline" to={`/test-center/runs/${startedRunId}`}>
                查看压测 run（受理 ≠ 完成，以 run 终态为准）
              </Link>
            ) : null}
            {startHint ? <span className="text-xs text-muted-foreground">{startHint}</span> : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>基线对比</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor="perf-baseline-p95">基线 p95（ms）</Label>
              <Input
                id="perf-baseline-p95"
                className="w-40"
                value={get("baselineP95")}
                onChange={(event) => set({ baselineP95: event.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="perf-baseline-tolerance">容忍度（RT 比例）</Label>
              <Input
                id="perf-baseline-tolerance"
                className="w-40"
                value={get("baselineTolerance")}
                onChange={(event) => set({ baselineTolerance: event.target.value })}
              />
            </div>
            <Button
              variant="outline"
              onClick={() => baselineMutation.mutate()}
              disabled={baselineMutation.isPending || !scenarioId}
            >
              创建基线（自动停用旧活跃）
            </Button>
          </div>
          {!scenarioId ? (
            <Alert>
              <AlertDescription>填写场景用例 ID 后查询基线（API-056）。</AlertDescription>
            </Alert>
          ) : (
            <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P16}>
              {items.length === 0 ? (
                <EmptyState title="无性能基线" />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>基线</TableHead>
                      <TableHead>p95（ms）</TableHead>
                      <TableHead>状态</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((item, index) => {
                      const metrics =
                        item.metrics_snapshot && typeof item.metrics_snapshot === "object"
                          ? (item.metrics_snapshot as Record<string, unknown>)
                          : {};
                      return (
                        <TableRow key={String(item.id ?? index)}>
                          <TableCell className="font-mono text-xs">{String(item.id ?? "")}</TableCell>
                          <TableCell className="font-mono text-xs">
                            {String(metrics.p95_ms ?? "—")}
                          </TableCell>
                          <TableCell>
                            {item.is_active === true ? (
                              <Badge>活跃</Badge>
                            ) : (
                              <Badge variant="outline">已停用</Badge>
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              )}
            </QueryGate>
          )}
        </CardContent>
      </Card>

      <div className="text-xs text-muted-foreground">
        <StatusBadge status="performance" /> 压力机自监控区分「目标慢 vs 施压机饱和」，结论以服务端 perf_report 为准。
      </div>

      <AlertDialog open={killOpen} onOpenChange={setKillOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>立即关停压测模块？</AlertDialogTitle>
            <AlertDialogDescription>
              关停走 API-199（L1 即时，60s 内停止全部施压进程）。恢复须走 kill_switch_restore，不能用 tighten 放开。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={tighten}>立即关停</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
