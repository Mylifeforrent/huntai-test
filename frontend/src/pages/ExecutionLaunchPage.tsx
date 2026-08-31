import { useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, Terminal } from "lucide-react";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import { isUndeveloped } from "@/api/errors";
import type { ListEnvelope, ResourceEnvelope } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { CommandFeedback, PageHeader, EmptyState, LoadingState, ErrorState } from "@/components/domain/PageState";
import { UndevelopedCallout } from "@/components/domain/UndevelopedCallout";
import { useUrlState } from "@/hooks/useUrlState";
import { asRecord, extractResourceId } from "@/lib/utils";
import { cn } from "@/lib/utils";

type Mode = "script" | "agent";

const PROJECT_APIS = PAGE_APIS.P08.filter((item) => item.id === "API-011");
const OPTIONS_APIS = PAGE_APIS.P08.filter((item) => item.id === "API-069");
const LAUNCH_APIS = PAGE_APIS.P08.filter((item) => item.id === "API-062");

export function ExecutionLaunchPage() {
  const { get, set } = useUrlState();
  const projectId = get("projectId");
  const urlCaseId = get("caseId");
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("script");
  const [envId, setEnvId] = useState("");
  const [caseIds, setCaseIds] = useState<string[]>(urlCaseId ? [urlCaseId] : []);
  const [targetEnv, setTargetEnv] = useState("");
  const [localError, setLocalError] = useState("");
  const [launchError, setLaunchError] = useState<unknown>(null);

  const projects = useQuery({
    queryKey: queryKeys.projects,
    queryFn: () => api.get<ListEnvelope<Record<string, unknown>>>("API-011", "/api/v1/projects"),
  });
  const options = useQuery({
    queryKey: queryKeys.executionOptions(projectId || "none"),
    queryFn: () =>
      api.get<ResourceEnvelope<Record<string, unknown>>>(
        "API-069",
        `/api/v1/projects/${projectId}/execution-options`,
      ),
    enabled: Boolean(projectId),
  });

  const projectItems = projects.data?.data.items ?? [];
  const projectsFailed = Boolean(projects.error) && !projects.isPending;
  const projectsUndeveloped = isUndeveloped(projects.error);

  const optionData = options.data?.data;
  const environments = Array.isArray(optionData?.environments) ? optionData.environments : [];
  const cases = Array.isArray(optionData?.cases) ? optionData.cases : [];
  const selected = environments
    .map((item) => asRecord(item))
    .find((item) => String(item.id) === envId);
  const envStatus = String(selected?.status ?? "");
  const envType = String(selected?.env_type ?? "");
  const envSelectable = selected?.selectable === true && envStatus === "ACTIVE";
  const agentBlocked = envType === "external_ci";
  const optionsFailed = Boolean(projectId) && Boolean(options.error) && !options.isPending;
  const optionsUndeveloped = isUndeveloped(options.error);

  const selectableCaseIds = useMemo(() => {
    const ids = new Set<string>();
    for (const item of cases) {
      const row = asRecord(item);
      if (row.selectable === true && typeof row.id === "string") {
        ids.add(row.id);
      }
    }
    return ids;
  }, [cases]);

  const chosenCaseIds = caseIds.filter((id) => selectableCaseIds.has(id));

  const launch = useMutation({
    mutationFn: () =>
      api.post("API-062", "/api/v1/test-runs", {
        project_id: projectId,
        env_id: envId,
        execution_source: mode === "agent" ? "agent" : "script",
        trigger_type: "manual",
        case_ids: chosenCaseIds,
        params: { TARGET_ENV: targetEnv },
      }),
    onMutate: () => setLaunchError(null),
    onSuccess: (payload) => {
      const id = extractResourceId(payload);
      if (id) {
        navigate(`/test-center/runs/${id}`);
        return;
      }
      setLaunchError(new Error("受理响应未返回 test_run_id，前端不视为发起成功"));
    },
    onError: (error) => setLaunchError(error),
  });

  function submit() {
    setLaunchError(null);
    if (!projectId) {
      setLocalError("请选择项目（API-011）或通过 ?projectId= 进入");
      return;
    }
    if (!envSelectable) {
      setLocalError("仅 ACTIVE 且 selectable 的环境可选");
      return;
    }
    if (mode === "agent" && agentBlocked) {
      setLocalError("外部 CI 一期不支持 Agent");
      return;
    }
    if (chosenCaseIds.length === 0) {
      setLocalError("至少选择一条服务端下发且 selectable 的用例（case_ids）");
      return;
    }
    if (!targetEnv.trim()) {
      setLocalError("TARGET_ENV 未通过本地即时校验");
      return;
    }
    setLocalError("");
    launch.mutate();
  }

  function toggleCase(id: string, checked: boolean) {
    setCaseIds((current) => {
      if (checked) {
        return current.includes(id) ? current : [...current, id];
      }
      return current.filter((item) => item !== id);
    });
  }

  return (
    <>
      <PageHeader title="发起执行" description="三层顺序冻结：模式 → 环境 → 参数表单。项目来自 API-011 或 ?projectId=" />
      <Card>
        <CardHeader>
          <CardTitle>项目</CardTitle>
          <CardDescription>/test-center/kickoff 无路径参数；从 API-011 选择或读取 URL projectId，不发明项目。</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {projects.isPending ? <LoadingState rows={1} /> : null}
          {projectsFailed && projectsUndeveloped ? (
            <UndevelopedCallout apis={PROJECT_APIS} error={projects.error} action="项目列表" />
          ) : null}
          {projectsFailed && !projectsUndeveloped ? <ErrorState error={projects.error} /> : null}
          {!projects.isPending && !projectsFailed && projectItems.length === 0 ? (
            <EmptyState compact title="无项目" hint="空集表示当前用户无项目成员身份。无手工建项目。" />
          ) : null}
          {!projects.isPending && !projectsFailed && projectItems.length > 0 ? (
            <Select value={projectId || undefined} onValueChange={(value) => set({ projectId: value })}>
              <SelectTrigger className="max-w-md">
                <SelectValue placeholder="选择项目（API-011）" />
              </SelectTrigger>
              <SelectContent>
                {projectItems.map((item) => {
                  const row = asRecord(item);
                  const id = typeof row.id === "string" ? row.id : "";
                  if (!id) {
                    return null;
                  }
                  return (
                    <SelectItem key={id} value={id}>
                      {String(row.name ?? id)}
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          ) : null}
          {!projectId ? (
            <Alert>
              <AlertDescription>执行选项（API-069）依赖 project_id。可从项目用例页带 ?projectId= 进入。</AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      {optionsFailed && optionsUndeveloped ? (
        <UndevelopedCallout apis={OPTIONS_APIS} error={options.error} action="执行选项" />
      ) : null}
      {optionsFailed && !optionsUndeveloped ? <ErrorState error={options.error} /> : null}

      <Layer step="1" title="执行模式" hint="Script 进门禁；Agent 不进门禁、无自动重试">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <ModeCard
            active={mode === "script"}
            title="Script Mode"
            hint="确定性执行 · 进质量门禁 · 可作为发布证据"
            icon={<Terminal className="size-4" />}
            onClick={() => setMode("script")}
          />
          <ModeCard
            active={mode === "agent"}
            disabled={agentBlocked}
            title="Agent Mode"
            hint="AI 动态执行 · 不进门禁 · 无自动重试"
            icon={<Bot className="size-4" />}
            onClick={() => {
              if (!agentBlocked) setMode("agent");
            }}
          />
        </div>
        {mode === "agent" ? (
          <div className="rounded-md border border-primary/20 bg-accent p-3 text-xs text-accent-foreground">
            <p>· Skill manifest：allowedTools / max_steps / sideEffectLevel ≤ L1</p>
            <p>· L2+ 工具动作单独进审批（TestRun → WAITING_APPROVAL）</p>
            <p>· execution_source=agent，不进质量门禁，不作为发布证据</p>
            <p>· Agent 任务无自动重试</p>
          </div>
        ) : null}
      </Layer>

      <Layer step="2" title="环境选择" hint="仅 ACTIVE 可选；DEGRADED / DISABLED / PENDING_APPROVAL 置灰">
        {!projectId ? (
          <EmptyState compact title="先选择项目" hint="环境列表来自 API-069，不发明环境。" />
        ) : options.isPending ? (
          <LoadingState rows={3} />
        ) : optionsFailed ? (
          <p className="text-xs text-muted-foreground">执行选项请求失败，不把失败当成空环境列表。</p>
        ) : environments.length === 0 ? (
          <EmptyState compact title="无可用环境" hint="空集是服务端下发，不是前端占位。" />
        ) : (
          <div className="flex flex-col gap-2">
            {environments.map((item, index) => {
              const row = asRecord(item);
              const id = String(row.id ?? index);
              const status = String(row.status ?? "");
              const disabled = row.selectable !== true || status !== "ACTIVE";
              const selectedEnv = envId === id;
              const health = asRecord(row.health_status);
              const capacity = asRecord(row.capacity);
              return (
                <button
                  key={id}
                  type="button"
                  disabled={disabled}
                  onClick={() => setEnvId(id)}
                  className={cn(
                    "flex items-start gap-3 rounded-md border-2 p-3 text-left transition-colors",
                    selectedEnv ? "border-primary bg-accent" : "border-border hover:border-primary/40",
                    disabled ? "cursor-not-allowed opacity-50" : "",
                  )}
                >
                  <span
                    className={cn(
                      "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border",
                      selectedEnv ? "border-primary bg-primary" : "border-muted-foreground/40",
                    )}
                  >
                    {selectedEnv ? <span className="size-1.5 rounded-full bg-primary-foreground" /> : null}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium">{String(row.name ?? id)}</span>
                      <StatusBadge status={status} />
                      {row.env_type ? (
                        <span className="font-mono text-[10px] text-muted-foreground">{String(row.env_type)}</span>
                      ) : null}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      health_status / 容量由服务端下发。
                      {typeof health.latency_ms === "number" ? ` · ${health.latency_ms}ms` : ""}
                      {typeof row.unavailable_reason === "string" ? ` · ${row.unavailable_reason}` : ""}
                      {Object.keys(capacity).length > 0 ? ` · capacity ${JSON.stringify(capacity)}` : ""}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>
        )}
        {envStatus && envStatus !== "ACTIVE" ? (
          <Button
            variant="outline"
            onClick={() => navigate(projectId ? `/projects/${projectId}/environments` : "/admin/environments")}
          >
            前往环境管理
          </Button>
        ) : null}
      </Layer>

      <Layer step="3" title="参数表单" hint="TARGET_ENV 本地即时校验；用例来自 API-069 cases，提交走 API-062">
        <div className="flex flex-col gap-2">
          <Label>用例（case_ids，仅 selectable）</Label>
          {!projectId || options.isPending || optionsFailed ? (
            <p className="text-xs text-muted-foreground">用例可选性随执行选项下发；查询失败不展示空成功列表。</p>
          ) : cases.length === 0 ? (
            <EmptyState compact title="无用例选项" hint="空集是服务端下发。" />
          ) : (
            cases.map((item, index) => {
              const row = asRecord(item);
              const id = typeof row.id === "string" ? row.id : "";
              if (!id) {
                return null;
              }
              const disabled = row.selectable !== true;
              const checked = chosenCaseIds.includes(id);
              return (
                <label
                  key={id}
                  className={cn(
                    "flex items-start gap-2 rounded-md border p-2 text-sm",
                    disabled ? "opacity-50" : "",
                  )}
                >
                  <Checkbox
                    checked={checked}
                    disabled={disabled}
                    onCheckedChange={(value) => toggleCase(id, value === true)}
                  />
                  <span>
                    {String(row.title ?? id)}
                    {typeof row.unavailable_reason === "string" ? (
                      <span className="ml-2 text-xs text-muted-foreground">{row.unavailable_reason}</span>
                    ) : null}
                  </span>
                  <span className="sr-only">{index}</span>
                </label>
              );
            })
          )}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="target-env">TARGET_ENV（必填，本地即时校验）</Label>
          <Input
            id="target-env"
            value={targetEnv}
            aria-invalid={Boolean(localError)}
            onChange={(event) => setTargetEnv(event.target.value)}
            placeholder="目标环境 URL"
          />
          {localError ? <p className="text-xs text-destructive">{localError}</p> : null}
        </div>
        <p className="text-xs text-muted-foreground">
          引用型用例按 params_schema_ref 动态生成（API-070）。定时配置仅本地编辑，提交走 API-062。前端不伪造受理成功。
        </p>
      </Layer>

      <div className="flex flex-col gap-3">
        <Button onClick={submit} disabled={launch.isPending}>
          发起执行
        </Button>
        <CommandFeedback error={launchError} apis={LAUNCH_APIS} action="创建 TestRun" />
      </div>
    </>
  );
}

function Layer({
  step,
  title,
  hint,
  children,
}: {
  step: string;
  title: string;
  hint: string;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="flex-row items-start gap-3">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary font-mono text-xs font-semibold text-primary-foreground">
          {step}
        </span>
        <div className="flex min-w-0 flex-col gap-1">
          <CardTitle>{title}</CardTitle>
          <CardDescription>{hint}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">{children}</CardContent>
    </Card>
  );
}

function ModeCard({
  active,
  disabled,
  title,
  hint,
  icon,
  onClick,
}: {
  active: boolean;
  disabled?: boolean;
  title: string;
  hint: string;
  icon: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex items-start gap-3 rounded-lg border-2 p-4 text-left transition-colors",
        active ? "border-primary bg-accent" : "border-border hover:border-primary/40",
        disabled ? "cursor-not-allowed opacity-50" : "",
      )}
    >
      <span
        className={cn(
          "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border",
          active ? "border-primary bg-primary" : "border-muted-foreground/40",
        )}
      >
        {active ? <span className="size-1.5 rounded-full bg-primary-foreground" /> : null}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">{icon}</span>
          <p className="text-sm font-semibold">{title}</p>
        </div>
        <p className="text-xs text-muted-foreground">{hint}</p>
        {disabled ? <p className="text-[10px] text-warning">当前环境不支持 Agent</p> : null}
      </div>
    </button>
  );
}
