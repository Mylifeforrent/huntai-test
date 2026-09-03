import { useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type {
  EnvironmentHealthProjection,
  ExecutionEnvironmentDetail,
  ExecutionEnvironmentListItem,
  ExecutionEnvironmentRegisterResult,
  JobContractListItem,
  JobParamsSchema,
  ListEnvelope,
  ResourceEnvelope,
} from "@/api/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CommandFeedback, PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { useUrlState } from "@/hooks/useUrlState";
import { useSession } from "@/hooks/useSession";

const ENV_TYPES = ["platform_executor", "external_ci"] as const;
const SCOPE_LEVELS = ["organization", "project"] as const;
const STATUS_FILTERS = ["", "PENDING_APPROVAL", "ACTIVE", "DEGRADED", "DISABLED"] as const;

export function EnvironmentPage() {
  const { projectId: routeProjectId } = useParams();
  const location = useLocation();
  const adminView = location.pathname.startsWith("/admin");
  const queryClient = useQueryClient();
  const { get, set } = useUrlState();
  const session = useSession();
  const statusFilter = get("status");
  const envTypeFilter = get("envType");

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [registerError, setRegisterError] = useState<unknown>(null);
  const [disableError, setDisableError] = useState<unknown>(null);
  const [name, setName] = useState("");
  const [envType, setEnvType] = useState<string>(ENV_TYPES[0]);
  const [scopeLevel, setScopeLevel] = useState<string>(SCOPE_LEVELS[0]);
  const [endpoint, setEndpoint] = useState("");
  const [adminProjectId, setAdminProjectId] = useState("");
  const [jobId, setJobId] = useState("");
  const [jobSchemaJson, setJobSchemaJson] = useState('{"type":"object","properties":{}}');
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

  const registerProjectId = adminView ? adminProjectId.trim() : (routeProjectId ?? "");

  const canManage =
    session.me?.memberships.some(
      (membership) =>
        membership.project_id === registerProjectId &&
        (membership.role === "owner" || membership.role === "admin"),
    ) ?? false;

  const listQuery = useQuery({
    queryKey: queryKeys.environments({
      projectId: routeProjectId ?? "",
      view: adminView ? "admin" : "project",
      status: statusFilter,
      envType: envTypeFilter,
    }),
    queryFn: () =>
      api.get<ListEnvelope<ExecutionEnvironmentListItem>>("API-100", "/api/v1/execution-environments", {
        project_id: adminView ? undefined : routeProjectId || undefined,
        status: statusFilter || undefined,
        env_type: envTypeFilter || undefined,
      }),
  });
  const items = listQuery.data?.data.items ?? [];

  const detailQuery = useQuery({
    queryKey: [...queryKeys.environments({}), "detail", selectedId ?? ""],
    queryFn: () =>
      api.get<ResourceEnvelope<ExecutionEnvironmentDetail>>(
        "API-101",
        `/api/v1/execution-environments/${selectedId}`,
      ),
    enabled: selectedId !== null,
  });

  const jobsQuery = useQuery({
    queryKey: [...queryKeys.environments({}), "jobs", selectedId ?? ""],
    queryFn: () =>
      api.get<ListEnvelope<JobContractListItem>>(
        "API-104",
        `/api/v1/execution-environments/${selectedId}/jobs`,
      ),
    enabled: selectedId !== null,
  });

  const healthQuery = useQuery({
    queryKey: [...queryKeys.environments({}), "health", selectedId ?? ""],
    queryFn: () =>
      api.get<ResourceEnvelope<EnvironmentHealthProjection>>(
        "API-105",
        `/api/v1/execution-environments/${selectedId}/health`,
      ),
    enabled: selectedId !== null,
  });

  const paramsSchemaQuery = useQuery({
    queryKey: [...queryKeys.environments({}), "schema", selectedId ?? "", selectedJobId ?? ""],
    queryFn: () =>
      api.get<ResourceEnvelope<JobParamsSchema>>(
        "API-070",
        `/api/v1/execution-environments/${selectedId}/jobs/${selectedJobId}/params-schema`,
      ),
    enabled: selectedId !== null && selectedJobId !== null,
  });

  const register = useMutation({
    mutationFn: () => {
      if (!registerProjectId) {
        return Promise.reject(new Error("project_id required"));
      }
      let schema: Record<string, unknown> | undefined;
      if (jobId.trim()) {
        try {
          schema = JSON.parse(jobSchemaJson) as Record<string, unknown>;
        } catch {
          return Promise.reject(new Error("invalid job schema JSON"));
        }
      }
      const body: Record<string, unknown> = {
        name: name.trim(),
        env_type: envType,
        scope_level: scopeLevel,
        project_id: registerProjectId,
      };
      if (endpoint.trim()) {
        body.endpoint = endpoint.trim();
      }
      if (jobId.trim()) {
        body.job_contracts = [
          {
            job_id: jobId.trim(),
            supports_cancel: true,
            contract_version: 1,
            report_adapter: envType === "external_ci" ? "junit" : undefined,
            schema,
          },
        ];
      }
      return api.post<ResourceEnvelope<ExecutionEnvironmentRegisterResult>>(
        "API-102",
        "/api/v1/execution-environments",
        body,
      );
    },
    onMutate: () => setRegisterError(null),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["execution-environments"] });
      setName("");
      setEndpoint("");
      setJobId("");
    },
    onError: (error) => setRegisterError(error),
  });

  const disableEnv = useMutation({
    mutationFn: (env: ExecutionEnvironmentDetail) =>
      api.post<ResourceEnvelope<ExecutionEnvironmentRegisterResult>>(
        "API-103",
        `/api/v1/execution-environments/${env.id}/disable`,
        { expected_version: env.version },
      ),
    onMutate: () => setDisableError(null),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["execution-environments"] });
      if (selectedId) {
        void detailQuery.refetch();
        void healthQuery.refetch();
      }
    },
    onError: (error) => setDisableError(error),
  });

  const detail = detailQuery.data?.data;
  const jobs = jobsQuery.data?.data.items ?? [];
  const health = healthQuery.data?.data;
  const canDisableSelected =
    canManage &&
    detail !== undefined &&
    (detail.status === "ACTIVE" || detail.status === "DEGRADED");

  const schemaPreview = useMemo(() => {
    const schema = paramsSchemaQuery.data?.data.schema;
    if (!schema) return "";
    try {
      return JSON.stringify(schema, null, 2);
    } catch {
      return "";
    }
  }, [paramsSchemaQuery.data?.data.schema]);

  return (
    <>
      <PageHeader
        title="环境管理"
        description="执行环境注册（健康检查、Job 发现）· 管理员审批。Admin 与 Projects 双入口同一页面。"
        actions={<span className="text-xs text-muted-foreground">{adminView ? "组织级视图" : "项目过滤视图"}</span>}
      />

      <Card className="mb-4">
        <CardHeader>
          <CardTitle className="text-base">筛选</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="filter-status">状态</Label>
            <select
              id="filter-status"
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={statusFilter}
              onChange={(e) => set({ status: e.target.value })}
            >
              {STATUS_FILTERS.map((value) => (
                <option key={value || "all"} value={value}>
                  {value || "全部"}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="filter-env-type">类型</Label>
            <select
              id="filter-env-type"
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={envTypeFilter}
              onChange={(e) => set({ envType: e.target.value })}
            >
              <option value="">全部</option>
              {ENV_TYPES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
        </CardContent>
      </Card>

      <QueryGate isPending={listQuery.isPending} error={listQuery.error} apis={PAGE_APIS.P15}>
        {items.length === 0 ? (
          <EmptyState title="无执行环境" />
        ) : (
          <div className="flex flex-col gap-3">
            {items.map((item) => (
              <Card
                key={item.id}
                className={selectedId === item.id ? "border-primary" : undefined}
              >
                <CardContent className="flex flex-wrap items-start justify-between gap-3 p-4">
                  <button
                    type="button"
                    className="flex flex-col gap-1 text-left"
                    onClick={() => {
                      setSelectedId(item.id);
                      setSelectedJobId(null);
                    }}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold">{item.name}</span>
                      <StatusBadge status={item.status} />
                      <span className="font-mono text-xs text-muted-foreground">{item.env_type}</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {item.scope_level} · v{item.version}
                      {item.credential_present ? " · 已绑定凭证引用" : ""}
                    </p>
                  </button>
                  {item.status === "PENDING_APPROVAL" ? (
                    <Button size="sm" variant="outline" asChild>
                      <Link to="/approvals">管理员审批</Link>
                    </Button>
                  ) : null}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </QueryGate>

      {selectedId && detail ? (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle className="text-base">环境详情 · {detail.name}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="text-sm text-muted-foreground">
              状态 <StatusBadge status={detail.status} /> · 健康投影{" "}
              {health?.health_status ? JSON.stringify(health.health_status) : "（M0 无探活）"}
            </div>
            {canDisableSelected ? (
              <Button
                variant="destructive"
                size="sm"
                className="w-fit"
                disabled={disableEnv.isPending}
                onClick={() => disableEnv.mutate(detail)}
              >
                停用环境
              </Button>
            ) : null}
            <div>
              <h3 className="mb-2 text-sm font-semibold">Job Registry</h3>
              {jobs.length === 0 ? (
                <p className="text-xs text-muted-foreground">无 Job 契约</p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {jobs.map((job) => (
                    <li key={job.job_id}>
                      <button
                        type="button"
                        className="text-sm text-primary underline-offset-4 hover:underline"
                        onClick={() => setSelectedJobId(job.job_id)}
                      >
                        {job.job_id}
                      </button>
                      <span className="ml-2 text-xs text-muted-foreground">
                        v{job.contract_version}
                        {job.supports_cancel ? " · 可取消" : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {selectedJobId && paramsSchemaQuery.data ? (
              <div>
                <h3 className="mb-2 text-sm font-semibold">参数 Schema（API-070）</h3>
                <pre className="max-h-48 overflow-auto rounded-md bg-muted p-3 text-xs">{schemaPreview}</pre>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>注册执行环境</CardTitle>
        </CardHeader>
        <CardContent className="flex max-w-lg flex-col gap-3">
          <Alert>
            <AlertDescription>
              新环境须经内联 L3 Gate（env_register）。创建后为 PENDING_APPROVAL，审批通过后变为 ACTIVE。
            </AlertDescription>
          </Alert>
          {adminView ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="admin-project-id">审批项目 ID（必填）</Label>
              <Input
                id="admin-project-id"
                value={adminProjectId}
                onChange={(e) => setAdminProjectId(e.target.value)}
                placeholder="用于四眼审批的项目 UUID"
              />
            </div>
          ) : null}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="env-name">名称</Label>
            <Input id="env-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="env-type">类型</Label>
            <select
              id="env-type"
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={envType}
              onChange={(e) => setEnvType(e.target.value)}
            >
              {ENV_TYPES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="scope-level">作用域</Label>
            <select
              id="scope-level"
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={scopeLevel}
              onChange={(e) => setScopeLevel(e.target.value)}
            >
              {SCOPE_LEVELS.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="env-endpoint">Endpoint（非密钥）</Label>
            <Input id="env-endpoint" value={endpoint} onChange={(e) => setEndpoint(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="job-id">可选 Job ID</Label>
            <Input id="job-id" value={jobId} onChange={(e) => setJobId(e.target.value)} />
          </div>
          {jobId.trim() ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="job-schema">Job Schema JSON</Label>
              <textarea
                id="job-schema"
                className="min-h-24 rounded-md border border-input bg-background p-2 font-mono text-xs"
                value={jobSchemaJson}
                onChange={(e) => setJobSchemaJson(e.target.value)}
              />
            </div>
          ) : null}
          <Button
            onClick={() => register.mutate()}
            disabled={register.isPending || !name.trim() || !registerProjectId || !canManage}
          >
            提交注册
          </Button>
          {!canManage && registerProjectId ? (
            <p className="text-xs text-muted-foreground">需要该项目 owner/admin 角色方可注册。</p>
          ) : null}
        </CardContent>
      </Card>
      <CommandFeedback error={registerError} apis={PAGE_APIS.P15} action="环境注册 API-102" />
      <CommandFeedback error={disableError} apis={PAGE_APIS.P15} action="环境停用 API-103" />
    </>
  );
}
