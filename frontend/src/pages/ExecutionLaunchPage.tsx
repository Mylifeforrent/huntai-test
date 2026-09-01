import { useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, Terminal } from "lucide-react";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import { isUndeveloped } from "@/api/errors";
import type {
  ExecutionEnvironmentListItem,
  ListEnvelope,
  ResourceEnvelope,
  TestRunStartResult,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
const ENV_APIS = PAGE_APIS.P15.filter((item) => item.id === "API-100");
const LAUNCH_APIS = PAGE_APIS.P08.filter((item) => item.id === "API-062");

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function parseCaseIds(raw: string): string[] {
  return raw
    .split(/[,\s]+/)
    .map((item) => item.trim())
    .filter((item) => UUID_RE.test(item));
}

export function ExecutionLaunchPage() {
  const { get, set } = useUrlState();
  const projectId = get("projectId");
  const urlCaseId = get("caseId");
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("script");
  const [envId, setEnvId] = useState("");
  const [caseIdsInput, setCaseIdsInput] = useState(urlCaseId ?? "");
  const [targetEnv, setTargetEnv] = useState("");
  const [localError, setLocalError] = useState("");
  const [launchError, setLaunchError] = useState<unknown>(null);

  const projects = useQuery({
    queryKey: queryKeys.projects,
    queryFn: () => api.get<ListEnvelope<Record<string, unknown>>>("API-011", "/api/v1/projects"),
  });
  const environments = useQuery({
    queryKey: queryKeys.environments({ projectId: projectId || "" }),
    queryFn: () =>
      api.get<ListEnvelope<ExecutionEnvironmentListItem>>("API-100", "/api/v1/execution-environments", {
        project_id: projectId || undefined,
      }),
    enabled: Boolean(projectId),
  });

  const projectItems = projects.data?.data.items ?? [];
  const projectsFailed = Boolean(projects.error) && !projects.isPending;
  const projectsUndeveloped = isUndeveloped(projects.error);

  const envItems = environments.data?.data.items ?? [];
  const selected = envItems.find((item) => item.id === envId);
  const envStatus = selected?.status ?? "";
  const envType = selected?.env_type ?? "";
  const envSelectable = envStatus === "ACTIVE";
  const agentBlocked = envType === "external_ci";
  const envsFailed = Boolean(projectId) && Boolean(environments.error) && !environments.isPending;
  const envsUndeveloped = isUndeveloped(environments.error);

  const caseIds = useMemo(() => parseCaseIds(caseIdsInput), [caseIdsInput]);

  const launch = useMutation({
    mutationFn: () => {
      if (!selected) {
        throw new Error("未选择环境");
      }
      return api.post<ResourceEnvelope<TestRunStartResult>>("API-062", "/api/v1/test-runs", {
        project_id: projectId,
        env_id: envId,
        execution_source: mode === "agent" ? "agent" : "script",
        trigger_type: "manual",
        case_ids: caseIds,
        expected_env_version: selected.version,
        params: targetEnv.trim() ? { TARGET_ENV: targetEnv.trim() } : undefined,
      });
    },
    onMutate: () => setLaunchError(null),
    onSuccess: (payload) => {
      const id = extractResourceId(payload) ?? payload.data.id;
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
    if (!envSelectable || !selected) {
      setLocalError("仅 ACTIVE 环境可选");
      return;
    }
    if (mode === "agent" && agentBlocked) {
      setLocalError("外部 CI 一期不支持 Agent");
      return;
    }
    if (caseIds.length === 0) {
      setLocalError("至少输入一个有效 case_id（UUID，逗号或空格分隔）");
      return;
    }
    if (!targetEnv.trim()) {
      setLocalError("TARGET_ENV 未通过本地即时校验");
      return;
    }
    setLocalError("");
    launch.mutate();
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
              <AlertDescription>环境列表（API-100）依赖 project_id。可从项目用例页带 ?projectId= 进入。</AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      {envsFailed && envsUndeveloped ? (
        <UndevelopedCallout apis={ENV_APIS} error={environments.error} action="执行环境" />
      ) : null}
      {envsFailed && !envsUndeveloped ? <ErrorState error={environments.error} /> : null}

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
          <EmptyState compact title="先选择项目" hint="环境列表来自 API-100，不发明环境。" />
        ) : environments.isPending ? (
          <LoadingState rows={3} />
        ) : envsFailed ? (
          <p className="text-xs text-muted-foreground">环境列表请求失败，不把失败当成空环境列表。</p>
        ) : envItems.length === 0 ? (
          <EmptyState compact title="无可用环境" hint="空集是服务端下发，不是前端占位。" />
        ) : (
          <div className="flex flex-col gap-2">
            {envItems.map((row) => {
              const id = row.id;
              const status = row.status;
              const disabled = status !== "ACTIVE";
              const selectedEnv = envId === id;
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
                      <span className="text-sm font-medium">{row.name ?? id}</span>
                      <StatusBadge status={status} />
                      {row.env_type ? (
                        <span className="font-mono text-[10px] text-muted-foreground">{row.env_type}</span>
                      ) : null}
                    </div>
                    <p className="text-xs text-muted-foreground">环境状态由服务端下发；仅 ACTIVE 可选。</p>
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

      <Layer step="3" title="参数表单" hint="TARGET_ENV 本地即时校验；case_ids 手动输入 UUID，提交走 API-062">
        <div className="flex flex-col gap-2">
          <Label htmlFor="case-ids">用例 ID（case_ids，UUID）</Label>
          <Input
            id="case-ids"
            value={caseIdsInput}
            onChange={(event) => setCaseIdsInput(event.target.value)}
            placeholder="uuid1, uuid2 或 ?caseId= 预填"
          />
          <p className="text-xs text-muted-foreground">
            已解析 {caseIds.length} 个有效 UUID。TestCase 列表 API 未实现，不发明用例。
          </p>
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
