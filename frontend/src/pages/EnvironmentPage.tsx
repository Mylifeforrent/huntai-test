import { useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ListEnvelope } from "@/api/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CommandFeedback, PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { StatusBadge } from "@/components/domain/StatusBadge";

export function EnvironmentPage() {
  const { projectId } = useParams();
  const location = useLocation();
  const adminView = location.pathname.startsWith("/admin");
  const queryClient = useQueryClient();
  const [registerError, setRegisterError] = useState<unknown>(null);
  const [name, setName] = useState("");
  const [envType, setEnvType] = useState("platform_executor");

  const query = useQuery({
    queryKey: queryKeys.environments({ projectId: projectId ?? "", view: adminView ? "admin" : "project" }),
    queryFn: () =>
      api.get<ListEnvelope<Record<string, unknown>>>("API-100", "/api/v1/execution-environments", {
        project_id: projectId || undefined,
      }),
  });
  const items = query.data?.data.items ?? [];

  const register = useMutation({
    mutationFn: () =>
      api.post("API-102", "/api/v1/execution-environments", {
        name,
        env_type: envType,
        project_id: projectId || undefined,
      }),
    onMutate: () => setRegisterError(null),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["execution-environments"] });
    },
    onError: (error) => setRegisterError(error),
  });

  return (
    <>
      <PageHeader
        title="环境管理"
        description="执行环境注册（健康检查、Job 发现、配额）· 管理员审批。Admin 与 Projects 双入口同一页面。"
        actions={<span className="text-xs text-muted-foreground">{adminView ? "组织级视图" : "项目过滤视图"}</span>}
      />
      <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P15}>
        {items.length === 0 ? (
          <EmptyState title="无执行环境" />
        ) : (
          <div className="flex flex-col gap-3">
            {items.map((item, index) => {
              const id = String(item.id ?? index);
              const status = String(item.status ?? "");
              return (
                <Card key={id}>
                  <CardContent className="flex flex-wrap items-start justify-between gap-3 p-4">
                    <div className="flex flex-col gap-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold">{String(item.name ?? id)}</span>
                        <StatusBadge status={status} />
                        <span className="font-mono text-xs text-muted-foreground">{String(item.env_type ?? "")}</span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        健康 / Job / 配额由服务端投影。凭证字段永不返回。DEGRADED / DISABLED / PENDING_APPROVAL 不可选为执行目标。
                      </p>
                    </div>
                    {status === "PENDING_APPROVAL" ? (
                      <Button size="sm" variant="outline" asChild>
                        <Link to="/approvals">管理员审批</Link>
                      </Button>
                    ) : null}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </QueryGate>
      <Card>
        <CardHeader>
          <CardTitle>注册执行环境</CardTitle>
        </CardHeader>
        <CardContent className="flex max-w-lg flex-col gap-3">
          <Alert>
            <AlertDescription>新环境接入需 env_register 审批（L3）。API-102 创建 PENDING_APPROVAL，须经 API-120 Preview。</AlertDescription>
          </Alert>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="env-name">名称</Label>
            <Input id="env-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="env-type">类型</Label>
            <Input id="env-type" value={envType} onChange={(e) => setEnvType(e.target.value)} placeholder="platform_executor / external_ci" />
          </div>
          <Button onClick={() => register.mutate()} disabled={register.isPending || !name.trim()}>
            提交注册
          </Button>
        </CardContent>
      </Card>
      <CommandFeedback error={registerError} apis={PAGE_APIS.P15} action="环境注册 API-102" />
    </>
  );
}
