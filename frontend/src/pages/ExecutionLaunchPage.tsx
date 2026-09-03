import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, Terminal } from "lucide-react";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import { isUndeveloped } from "@/api/errors";
import type {
  ExecutionOptions,
  JobParamsSchema,
  ResourceEnvelope,
  TestRunStartResult,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { CommandFeedback, PageHeader, EmptyState, LoadingState } from "@/components/domain/PageState";
import { useUrlState } from "@/hooks/useUrlState";
import { asRecord, extractResourceId } from "@/lib/utils";
import { cn } from "@/lib/utils";

type Mode = "script" | "agent";

const PROJECT_APIS = PAGE_APIS.P08.filter((item) => item.id === "API-011");
const OPTIONS_APIS = PAGE_APIS.P08.filter((item) => item.id === "API-069");
const LAUNCH_APIS = PAGE_APIS.P08.filter((item) => item.id === "API-062");
const SCHEMA_APIS = PAGE_APIS.P08.filter((item) => item.id === "API-070");

function executionSourceFor(mode: Mode, envType: string | undefined): string {
  if (mode === "agent") return "agent";
  if (envType === "external_ci") return "external_ci";
  return "script";
}

function schemaRequiredFields(schema: Record<string, unknown> | undefined): string[] {
  if (!schema) return [];
  const required = schema.required;
  if (!Array.isArray(required)) return [];
  return required.filter((item): item is string => typeof item === "string");
}

export function ExecutionLaunchPage() {
  const { get, set } = useUrlState();
  const projectId = get("projectId");
  const urlCaseId = get("caseId");
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("script");
  const [envId, setEnvId] = useState("");
  const [selectedCaseIds, setSelectedCaseIds] = useState<string[]>(urlCaseId ? [urlCaseId] : []);
  const [targetEnv, setTargetEnv] = useState("");
  const [jobParams, setJobParams] = useState<Record<string, string>>({});
  const [localError, setLocalError] = useState("");
  const [launchError, setLaunchError] = useState<unknown>(null);

  const projects = useQuery({
    queryKey: queryKeys.projects,
    queryFn: () => api.get<{ data: { items: Record<string, unknown>[] } }>("API-011", "/api/v1/projects"),
  });

  const envItemsQuery = useQuery({
    queryKey: [...queryKeys.executionOptions(projectId || ""), "envs"],
    queryFn: () =>
      api.get<ResourceEnvelope<ExecutionOptions>>(
        "API-069",
        `/api/v1/projects/${projectId}/execution-options`,
        {},
      ),
    enabled: Boolean(projectId),
  });

  const envItems = envItemsQuery.data?.data.environments ?? [];
  const selected = envItems.find((item) => item.id === envId);
  const agentBlocked = selected?.env_type === "external_ci";
  const isExternalCi = selected?.env_type === "external_ci";

  const executionOptionsScoped = useQuery({
    queryKey: [
      ...queryKeys.executionOptions(projectId || ""),
      mode,
      selected?.env_type ?? "none",
    ],
    queryFn: () =>
      api.get<ResourceEnvelope<ExecutionOptions>>(
        "API-069",
        `/api/v1/projects/${projectId}/execution-options`,
        { execution_source: executionSourceFor(mode, selected?.env_type) },
      ),
    enabled: Boolean(projectId && selected?.selectable),
  });

  const scopedCaseItems = executionOptionsScoped.data?.data.cases ?? [];

  const projectItems = projects.data?.data.items ?? [];
  const primaryCaseId = selectedCaseIds[0] ?? "";
  const primaryCase = scopedCaseItems.find((item) => item.id === primaryCaseId);
  const primaryJobId = primaryCase?.job_id ?? null;

  const paramsSchemaQuery = useQuery({
    queryKey: [...queryKeys.environments({}), "launch-schema", envId, primaryJobId ?? ""],
    queryFn: () =>
      api.get<ResourceEnvelope<JobParamsSchema>>(
        "API-070",
        `/api/v1/execution-environments/${envId}/jobs/${primaryJobId}/params-schema`,
      ),
    enabled: Boolean(isExternalCi && envId && primaryJobId),
  });

  const requiredFields = useMemo(
    () => schemaRequiredFields(paramsSchemaQuery.data?.data.schema),
    [paramsSchemaQuery.data?.data.schema],
  );

  useEffect(() => {
    if (!isExternalCi) return;
    setJobParams((prev) => {
      const next: Record<string, string> = {};
      for (const field of requiredFields) {
        next[field] = prev[field] ?? "";
      }
      return next;
    });
  }, [isExternalCi, requiredFields.join("|")]);

  const launch = useMutation({
    mutationFn: () => {
      if (!selected) {
        throw new Error("未选择环境");
      }
      const params = isExternalCi
        ? Object.fromEntries(
            Object.entries(jobParams).map(([key, value]) => [key, value.trim()]),
          )
        : targetEnv.trim()
          ? { TARGET_ENV: targetEnv.trim() }
          : undefined;
      return api.post<ResourceEnvelope<TestRunStartResult>>("API-062", "/api/v1/test-runs", {
        project_id: projectId,
        env_id: envId,
        execution_source: executionSourceFor(mode, selected.env_type),
        trigger_type: "manual",
        case_ids: selectedCaseIds,
        expected_env_version: selected.version,
        params,
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

  const selectableCases = useMemo(
    () => scopedCaseItems.filter((item) => item.selectable),
    [scopedCaseItems],
  );

  function toggleCase(caseId: string, checked: boolean) {
    setSelectedCaseIds((prev) => {
      if (checked) {
        return prev.includes(caseId) ? prev : [...prev, caseId];
      }
      return prev.filter((id) => id !== caseId);
    });
  }

  function submit() {
    setLaunchError(null);
    if (!projectId) {
      setLocalError("请选择项目（API-011）或通过 ?projectId= 进入");
      return;
    }
    if (!selected?.selectable) {
      setLocalError("仅 ACTIVE 且 selectable 的环境可选（API-069）");
      return;
    }
    if (mode === "agent" && agentBlocked) {
      setLocalError("外部 CI 一期不支持 Agent");
      return;
    }
    if (selectedCaseIds.length === 0) {
      setLocalError("至少选择一个 ACTIVE 用例（API-069）");
      return;
    }
    if (isExternalCi) {
      for (const field of requiredFields) {
        if (!jobParams[field]?.trim()) {
          setLocalError(`Job 参数 ${field} 未通过本地即时校验`);
          return;
        }
      }
    } else if (!targetEnv.trim()) {
      setLocalError("TARGET_ENV 未通过本地即时校验");
      return;
    }
    setLocalError("");
    launch.mutate();
  }

  return (
    <>
      <PageHeader title="发起执行" description="三层顺序冻结：模式 → 环境 → 参数。环境与用例来自 API-069。" />
      <Card>
        <CardHeader>
          <CardTitle>项目</CardTitle>
        </CardHeader>
        <CardContent>
          {projects.isPending ? <LoadingState rows={1} /> : null}
          {projects.error && isUndeveloped(projects.error) ? (
            <CommandFeedback error={projects.error} apis={PROJECT_APIS} action="项目列表" />
          ) : null}
          {projectItems.length > 0 ? (
            <select
              className="max-w-md rounded-md border px-3 py-2 text-sm"
              value={projectId || ""}
              onChange={(event) => set({ projectId: event.target.value })}
            >
              <option value="">选择项目</option>
              {projectItems.map((item) => {
                const row = asRecord(item);
                const id = typeof row.id === "string" ? row.id : "";
                return (
                  <option key={id} value={id}>
                    {String(row.name ?? id)}
                  </option>
                );
              })}
            </select>
          ) : (
            <EmptyState compact title="无项目" hint="空集表示当前用户无项目成员身份。" />
          )}
        </CardContent>
      </Card>

      <Layer step="1" title="执行模式" hint="Script 进门禁；Agent 不进门禁">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <ModeCard
            active={mode === "script"}
            title="Script Mode"
            hint="确定性执行"
            icon={<Terminal className="size-4" />}
            onClick={() => setMode("script")}
          />
          <ModeCard
            active={mode === "agent"}
            disabled={agentBlocked}
            title="Agent Mode"
            hint="AI 动态执行"
            icon={<Bot className="size-4" />}
            onClick={() => {
              if (!agentBlocked) setMode("agent");
            }}
          />
        </div>
      </Layer>

      <Layer step="2" title="环境选择" hint="API-069：仅 selectable=true 可选">
        {!projectId ? (
          <EmptyState compact title="先选择项目" />
        ) : envItemsQuery.isPending ? (
          <LoadingState rows={3} />
        ) : envItemsQuery.error ? (
          <CommandFeedback error={envItemsQuery.error} apis={OPTIONS_APIS} action="执行选项" />
        ) : (
          <div className="flex flex-col gap-2">
            {envItems.map((row) => {
              const disabled = !row.selectable;
              const selectedEnv = envId === row.id;
              return (
                <button
                  key={row.id}
                  type="button"
                  disabled={disabled}
                  onClick={() => setEnvId(row.id)}
                  className={cn(
                    "flex items-start gap-3 rounded-md border-2 p-3 text-left",
                    selectedEnv ? "border-primary bg-accent" : "border-border",
                    disabled ? "cursor-not-allowed opacity-50" : "",
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium">{row.name}</span>
                      <StatusBadge status={row.status} />
                    </div>
                    {row.unavailable_reason ? (
                      <p className="text-xs text-muted-foreground">{row.unavailable_reason}</p>
                    ) : null}
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </Layer>

      <Layer
        step="3"
        title="参数表单"
        hint={isExternalCi ? "引用型用例 Job 参数（API-070）" : "用例多选 + TARGET_ENV；提交走 API-062"}
      >
        <div className="flex flex-col gap-2">
          <Label>用例（API-069）</Label>
          {scopedCaseItems.length === 0 ? (
            <EmptyState compact title="无用例选项" />
          ) : (
            scopedCaseItems.map((row) => (
              <label key={row.id} className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={selectedCaseIds.includes(row.id)}
                  disabled={!row.selectable}
                  onCheckedChange={(checked) => toggleCase(row.id, checked === true)}
                />
                <span className={row.selectable ? "" : "text-muted-foreground line-through"}>
                  {row.title} ({row.lifecycle_status})
                  {row.case_type ? ` · ${row.case_type}` : ""}
                </span>
              </label>
            ))
          )}
          <p className="text-xs text-muted-foreground">已选 {selectedCaseIds.length} 个；可选 {selectableCases.length} 个。</p>
        </div>
        {isExternalCi ? (
          <div className="flex flex-col gap-3">
            {paramsSchemaQuery.isPending ? <LoadingState rows={2} /> : null}
            {paramsSchemaQuery.error ? (
              <CommandFeedback error={paramsSchemaQuery.error} apis={SCHEMA_APIS} action="Job Schema" />
            ) : null}
            {requiredFields.map((field) => (
              <div key={field} className="flex flex-col gap-1.5">
                <Label htmlFor={`job-param-${field}`}>{field}（必填）</Label>
                <Input
                  id={`job-param-${field}`}
                  value={jobParams[field] ?? ""}
                  onChange={(event) =>
                    setJobParams((prev) => ({ ...prev, [field]: event.target.value }))
                  }
                />
              </div>
            ))}
            {requiredFields.length === 0 && primaryJobId ? (
              <p className="text-xs text-muted-foreground">API-070 未声明 required 字段。</p>
            ) : null}
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="target-env">TARGET_ENV（必填）</Label>
            <Input id="target-env" value={targetEnv} onChange={(event) => setTargetEnv(event.target.value)} />
          </div>
        )}
        {localError ? <p className="text-xs text-destructive">{localError}</p> : null}
      </Layer>

      <Button onClick={submit} disabled={launch.isPending}>
        发起执行
      </Button>
      <CommandFeedback error={launchError} apis={LAUNCH_APIS} action="创建 TestRun" />
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
      <CardHeader>
        <CardTitle>
          {step}. {title}
        </CardTitle>
        <CardDescription>{hint}</CardDescription>
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
        "rounded-lg border-2 p-4 text-left",
        active ? "border-primary bg-accent" : "border-border",
        disabled ? "opacity-50" : "",
      )}
    >
      <div className="flex items-center gap-2">
        {icon}
        <span className="font-semibold">{title}</span>
      </div>
      <p className="text-xs text-muted-foreground">{hint}</p>
    </button>
  );
}
