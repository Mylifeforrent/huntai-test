import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type {
  ListEnvelope,
  ResourceEnvelope,
  TestCaseListItem,
  TestPlanDetail,
  TestPlanListItem,
  TestPlanWriteResult,
} from "@/api/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CommandFeedback, MutateOnly, PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { useUrlState } from "@/hooks/useUrlState";
import { useSession } from "@/hooks/useSession";
import { useViewport } from "@/hooks/useViewport";

export function TestPlanPage() {
  const { projectId = "" } = useParams();
  const queryClient = useQueryClient();
  const { get, set } = useUrlState();
  const session = useSession();
  const { canMutate } = useViewport();
  const q = get("q");
  const cursor = get("cursor");
  const selectedPlanId = get("plan") || null;

  const [createError, setCreateError] = useState<unknown>(null);
  const [bindError, setBindError] = useState<unknown>(null);
  const [scheduleError, setScheduleError] = useState<unknown>(null);
  const [name, setName] = useState("");
  const [jiraFixVersion, setJiraFixVersion] = useState("");
  const [selectedCaseIds, setSelectedCaseIds] = useState<string[]>([]);
  const [scheduleEnabled, setScheduleEnabled] = useState(false);
  const [scheduleJson, setScheduleJson] = useState("{}");
  const [envId, setEnvId] = useState("");

  const canWrite =
    canMutate &&
    (session.me?.memberships.some(
      (membership) =>
        membership.project_id === projectId &&
        (membership.role === "owner" ||
          membership.role === "admin" ||
          membership.role === "tester"),
    ) ??
      false);

  const listQuery = useQuery({
    queryKey: queryKeys.testPlans({ projectId, q, cursor }),
    queryFn: () =>
      api.get<ListEnvelope<TestPlanListItem>>("API-050", "/api/v1/test-plans", {
        project_id: projectId,
        q: q || undefined,
        cursor: cursor || undefined,
      }),
    enabled: Boolean(projectId),
  });
  const items = listQuery.data?.data.items ?? [];

  const detailQuery = useQuery({
    queryKey: queryKeys.testPlan(selectedPlanId ?? ""),
    queryFn: () =>
      api.get<ResourceEnvelope<TestPlanDetail>>("API-051", `/api/v1/test-plans/${selectedPlanId}`),
    enabled: selectedPlanId !== null,
  });
  const detail = detailQuery.data?.data;

  const casesQuery = useQuery({
    queryKey: queryKeys.testCases({ projectId }),
    queryFn: () =>
      api.get<ListEnvelope<TestCaseListItem>>("API-030", "/api/v1/test-cases", {
        project_id: projectId,
      }),
    enabled: Boolean(projectId) && selectedPlanId !== null,
  });
  const caseItems = casesQuery.data?.data.items ?? [];

  const createPlan = useMutation({
    mutationFn: () =>
      api.post<ResourceEnvelope<TestPlanWriteResult>>("API-052", "/api/v1/test-plans", {
        project_id: projectId,
        name: name.trim(),
        jira_fix_version: jiraFixVersion.trim() || undefined,
      }),
    onMutate: () => setCreateError(null),
    onSuccess: (response) => {
      void queryClient.invalidateQueries({ queryKey: ["test-plans"] });
      setName("");
      setJiraFixVersion("");
      set({ plan: response.data.id });
    },
    onError: (error) => setCreateError(error),
  });

  const bindCases = useMutation({
    mutationFn: (plan: TestPlanDetail) =>
      api.put<ResourceEnvelope<TestPlanWriteResult>>(
        "API-054",
        `/api/v1/test-plans/${plan.id}/case-ids`,
        { expected_version: plan.version, case_ids: selectedCaseIds },
      ),
    onMutate: () => setBindError(null),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["test-plans"] });
      if (selectedPlanId) {
        void detailQuery.refetch();
      }
    },
    onError: (error) => setBindError(error),
  });

  const bindSchedule = useMutation({
    mutationFn: (plan: TestPlanDetail) => {
      let schedule: Record<string, unknown> | undefined;
      try {
        schedule = JSON.parse(scheduleJson) as Record<string, unknown>;
      } catch {
        return Promise.reject(new Error("invalid schedule JSON"));
      }
      const body: Record<string, unknown> = {
        expected_version: plan.version,
        enabled: scheduleEnabled,
        schedule,
      };
      if (envId.trim()) {
        body.env_id = envId.trim();
      }
      return api.put<ResourceEnvelope<TestPlanWriteResult>>(
        "API-055",
        `/api/v1/test-plans/${plan.id}/schedule`,
        body,
      );
    },
    onMutate: () => setScheduleError(null),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["test-plans"] });
      if (selectedPlanId) {
        void detailQuery.refetch();
      }
    },
    onError: (error) => setScheduleError(error),
  });

  const statusLabels = useMemo(() => {
    if (!detail) {
      return null;
    }
    const caseLabel =
      detail.case_ids.length > 0 ? `已绑定 ${detail.case_ids.length} 条` : "未绑定";
    const scheduleLabel = detail.schedule ? "已绑定" : "未绑定";
    const runLabel = detail.report_aggregate.last_run_id
      ? `最近 ${detail.report_aggregate.last_run_id}`
      : "未发起";
    return { caseLabel, scheduleLabel, runLabel };
  }, [detail]);

  useEffect(() => {
    if (detail) {
      setSelectedCaseIds(detail.case_ids);
      if (detail.schedule) {
        setScheduleEnabled(Boolean(detail.schedule.enabled));
        setScheduleJson(
          detail.schedule.schedule ? JSON.stringify(detail.schedule.schedule, null, 2) : "{}",
        );
        setEnvId(detail.schedule.env_id ?? "");
      }
    }
  }, [detail]);

  return (
    <>
      <PageHeader
        title="测试计划"
        description="计划编排（关联 Jira fixVersion）· 用例集选择 · 执行历史与计划级报告 · 定时回归绑定"
      />

      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="按名称筛选"
          value={q}
          onChange={(event) => set({ q: event.target.value, cursor: undefined })}
          className="max-w-56"
        />
      </div>

      <QueryGate isPending={listQuery.isPending} error={listQuery.error} apis={PAGE_APIS.P06}>
        {items.length === 0 ? (
          <EmptyState title="无测试计划" hint="空集是 200 + items: []，与请求失败不同" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>计划</TableHead>
                <TableHead>fixVersion</TableHead>
                <TableHead>用例数</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => (
                <TableRow
                  key={item.id}
                  className={selectedPlanId === item.id ? "bg-muted/40" : undefined}
                  onClick={() => set({ plan: item.id })}
                >
                  <TableCell>
                    <p className="font-medium">{item.name}</p>
                    <p className="font-mono text-xs text-muted-foreground">{item.id}</p>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{item.jira_fix_version ?? "—"}</TableCell>
                  <TableCell className="font-mono">{item.case_count}</TableCell>
                  <TableCell>
                    <MutateOnly>
                      <Button size="sm" asChild onClick={(event) => event.stopPropagation()}>
                        <Link to="/test-center/kickoff">执行</Link>
                      </Button>
                    </MutateOnly>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </QueryGate>

      {canWrite ? (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle className="text-base">创建测试计划</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 lg:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="plan-name">名称</Label>
              <Input
                id="plan-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="计划名称"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="plan-fix">Jira fixVersion（可选）</Label>
              <Input
                id="plan-fix"
                value={jiraFixVersion}
                onChange={(event) => setJiraFixVersion(event.target.value)}
                placeholder="例如 2.4.0"
              />
            </div>
            <div className="lg:col-span-2">
              <Button
                disabled={!name.trim() || createPlan.isPending}
                onClick={() => createPlan.mutate()}
              >
                创建计划
              </Button>
              <p className="mt-2 text-xs text-muted-foreground">
                创建成功 ≠ 用例已绑定 ≠ 定时已绑定 ≠ 可执行；请在下方面板逐步完成绑定。
              </p>
            </div>
            <CommandFeedback error={createError} apis={PAGE_APIS.P06} action="创建计划 API-052" />
          </CardContent>
        </Card>
      ) : (
        <Alert className="mt-4">
          <AlertDescription>当前角色仅可查看计划列表与详情，写操作已禁用。</AlertDescription>
        </Alert>
      )}

      {selectedPlanId ? (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle className="text-base">计划详情</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <QueryGate
              isPending={detailQuery.isPending}
              error={detailQuery.error}
              apis={PAGE_APIS.P06}
            >
              {detail && statusLabels ? (
                <>
                  <div className="grid gap-2 text-sm lg:grid-cols-2">
                    <p>
                      <span className="text-muted-foreground">已创建：</span>
                      {detail.name}（v{detail.version}）
                    </p>
                    <p>
                      <span className="text-muted-foreground">用例集：</span>
                      {statusLabels.caseLabel}
                    </p>
                    <p>
                      <span className="text-muted-foreground">定时：</span>
                      {statusLabels.scheduleLabel}
                    </p>
                    <p>
                      <span className="text-muted-foreground">执行：</span>
                      {statusLabels.runLabel}
                    </p>
                  </div>

                  {detail.report_aggregate.last_run_id === null ? (
                    <Alert>
                      <AlertDescription>
                        计划级结果缺口：尚无关联 TestRun（不得按通过）
                      </AlertDescription>
                    </Alert>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      最近 TestRun：{detail.report_aggregate.last_run_id} · 状态{" "}
                      {detail.report_aggregate.last_run_status ?? "—"}
                    </p>
                  )}

                  {canWrite ? (
                    <>
                      <div>
                        <p className="mb-2 text-sm font-medium">绑定用例（全量替换）</p>
                        <div className="max-h-48 space-y-1 overflow-y-auto rounded border p-2">
                          {caseItems.map((testCase) => {
                            const checked = selectedCaseIds.includes(testCase.id);
                            return (
                              <label key={testCase.id} className="flex items-center gap-2 text-sm">
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={() => {
                                    setSelectedCaseIds((prev) =>
                                      checked
                                        ? prev.filter((id) => id !== testCase.id)
                                        : [...prev, testCase.id],
                                    );
                                  }}
                                />
                                <span>{testCase.title}</span>
                                <span className="font-mono text-xs text-muted-foreground">
                                  {testCase.id}
                                </span>
                              </label>
                            );
                          })}
                        </div>
                        <Button
                          className="mt-2"
                          size="sm"
                          disabled={bindCases.isPending}
                          onClick={() => bindCases.mutate(detail)}
                        >
                          保存用例绑定
                        </Button>
                        <CommandFeedback error={bindError} apis={PAGE_APIS.P06} action="绑定用例 API-054" />
                      </div>

                      <div>
                        <p className="mb-2 text-sm font-medium">绑定定时</p>
                        <label className="mb-2 flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={scheduleEnabled}
                            onChange={(event) => setScheduleEnabled(event.target.checked)}
                          />
                          启用定时绑定
                        </label>
                        <div className="mb-2 flex flex-col gap-1.5">
                          <Label htmlFor="schedule-env">环境 ID（可选）</Label>
                          <Input
                            id="schedule-env"
                            value={envId}
                            onChange={(event) => setEnvId(event.target.value)}
                            placeholder="UUID"
                            className="font-mono text-xs"
                          />
                        </div>
                        <Label htmlFor="schedule-json">schedule JSON（不透明，无默认表达式）</Label>
                        <textarea
                          id="schedule-json"
                          className="mt-1 min-h-24 w-full rounded-md border border-input bg-background p-2 font-mono text-xs"
                          value={scheduleJson}
                          onChange={(event) => setScheduleJson(event.target.value)}
                          placeholder='{"note":"opaque binding"}'
                        />
                        <Button
                          className="mt-2"
                          size="sm"
                          disabled={bindSchedule.isPending}
                          onClick={() => bindSchedule.mutate(detail)}
                        >
                          保存定时绑定
                        </Button>
                        <CommandFeedback error={scheduleError} apis={PAGE_APIS.P06} action="定时绑定 API-055" />
                      </div>
                    </>
                  ) : null}

                  <Button size="sm" asChild>
                    <Link to="/test-center/kickoff">执行</Link>
                  </Button>
                </>
              ) : null}
            </QueryGate>
          </CardContent>
        </Card>
      ) : null}
    </>
  );
}
