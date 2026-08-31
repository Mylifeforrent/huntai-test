import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ListEnvelope } from "@/api/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { UndevelopedCallout } from "@/components/domain/UndevelopedCallout";

export function IntegrationPage() {
  const { projectId = "" } = useParams();
  const [bindTried, setBindTried] = useState(false);
  const [repo, setRepo] = useState("");
  const [branch, setBranch] = useState("");
  const [planId, setPlanId] = useState("");
  const [event, setEvent] = useState("push");

  const connectors = useQuery({
    queryKey: queryKeys.connectors({ projectId }),
    queryFn: () =>
      api.get<ListEnvelope<Record<string, unknown>>>("API-160", "/api/v1/connectors", {
        project_id: projectId || undefined,
      }),
    enabled: Boolean(projectId),
  });
  const items = connectors.data?.data.items ?? [];

  function saveBinding() {
    setBindTried(true);
    void api
      .put("API-167", `/api/v1/projects/${projectId}/ci-trigger-bindings`, {
        repo,
        branch,
        test_plan_id: planId,
        event,
      })
      .catch(() => undefined);
  }

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
            <Input id="repo" value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="org/repo" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="branch">分支</Label>
            <Input id="branch" value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="main" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="plan">测试计划 ID</Label>
            <Input id="plan" value={planId} onChange={(e) => setPlanId(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="event">触发事件</Label>
            <Input id="event" value={event} onChange={(e) => setEvent(e.target.value)} placeholder="push / pull_request" />
          </div>
          <Button onClick={saveBinding} disabled={!projectId}>
            保存绑定（API-167）
          </Button>
        </CardContent>
      </Card>
      {bindTried ? <UndevelopedCallout apis={PAGE_APIS.P03} action="CI 触发绑定" /> : null}
    </>
  );
}
