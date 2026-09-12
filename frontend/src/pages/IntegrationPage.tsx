import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ConnectorListItem, ListEnvelope } from "@/api/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CommandFeedback, MutateOnly, PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { StatusBadge } from "@/components/domain/StatusBadge";

type CiBindingsResponse = {
  project_id: string;
  version: number;
  bindings: Array<{
    repository: string;
    ref_pattern: string;
    test_plan_id: string;
    connector_id?: string;
  }>;
};

export function IntegrationPage() {
  const { projectId = "" } = useParams();
  const queryClient = useQueryClient();
  const [repository, setRepository] = useState("");
  const [refPattern, setRefPattern] = useState("");
  const [planId, setPlanId] = useState("");
  const [expectedVersion, setExpectedVersion] = useState(1);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const connectors = useQuery({
    queryKey: queryKeys.connectors({ scope: "project", projectId }),
    queryFn: () => api.get<ListEnvelope<ConnectorListItem>>("API-160", "/api/v1/connectors"),
    enabled: Boolean(projectId),
  });
  const items = connectors.data?.data.items ?? [];

  const saveMutation = useMutation({
    mutationFn: () =>
      api.put<{ data: CiBindingsResponse }>(
        "API-167",
        `/api/v1/projects/${projectId}/ci-trigger-bindings`,
        {
          expected_version: expectedVersion,
          bindings: [
            {
              repository,
              ref_pattern: refPattern,
              test_plan_id: planId,
            },
          ],
        },
      ),
    onSuccess: (response) => {
      setSaveError(null);
      setSaveSuccess(true);
      setExpectedVersion(response.data.version);
      void queryClient.invalidateQueries({ queryKey: queryKeys.connectors({ scope: "project", projectId }) });
    },
    onError: (error: unknown) => {
      setSaveSuccess(false);
      setSaveError(error);
    },
  });

  return (
    <>
      <PageHeader
        title="集成"
        description="GitHub 仓库/分支 ↔ 测试计划触发绑定 · 项目级连接器配置"
      />
      {!projectId ? (
        <Alert>
          <AlertDescription>项目级集成依赖路径中的 projectId。</AlertDescription>
        </Alert>
      ) : (
        <QueryGate isPending={connectors.isPending} error={connectors.error} apis={PAGE_APIS.P03}>
          <Card>
            <CardHeader>
              <CardTitle>项目级连接器</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {items.length === 0 ? <EmptyState title="无连接器" hint="组织级实例在管理/集成中心。" /> : null}
              {items.map((item, index) => {
                const id = String(item.id ?? index);
                return (
                  <div key={id} className="flex items-center justify-between rounded-md border p-3">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{String(item.name ?? id)}</span>
                      <StatusBadge status={String(item.type ?? "")} />
                    </div>
                    <StatusBadge status={item.outbound_write_enabled === true ? "ACTIVE" : "DISABLED"} />
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </QueryGate>
      )}
      <Card>
        <CardHeader>
          <CardTitle>CI 触发绑定</CardTitle>
        </CardHeader>
        <CardContent className="flex max-w-lg flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="repo">GitHub 仓库</Label>
            <Input id="repo" value={repository} onChange={(e) => setRepository(e.target.value)} placeholder="org/repo" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ref">分支 / ref 模式</Label>
            <Input id="ref" value={refPattern} onChange={(e) => setRefPattern(e.target.value)} placeholder="main" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="plan">测试计划 ID</Label>
            <Input id="plan" value={planId} onChange={(e) => setPlanId(e.target.value)} />
          </div>
          <MutateOnly>
            <Button onClick={() => saveMutation.mutate()} disabled={!projectId || saveMutation.isPending}>
              保存绑定（API-167）
            </Button>
          </MutateOnly>
          {saveSuccess ? (
            <Alert>
              <AlertDescription>绑定已保存（version={expectedVersion}）。本操作不会创建 TestRun。</AlertDescription>
            </Alert>
          ) : null}
          {saveError ? (
            <CommandFeedback error={saveError} apis={PAGE_APIS.P03} action="CI 触发绑定" />
          ) : null}
        </CardContent>
      </Card>
    </>
  );
}
