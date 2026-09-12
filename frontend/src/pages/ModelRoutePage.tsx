import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type {
  AIInvocationLogListItem,
  ConnectionTestResult,
  ListEnvelope,
  ModelRouteListItem,
  ResourceEnvelope,
} from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  CommandFeedback,
  EmptyState,
  MutateOnly,
  PageHeader,
  QueryGate,
} from "@/components/domain/PageState";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { useUrlState } from "@/hooks/useUrlState";

export function ModelRoutePage() {
  const queryClient = useQueryClient();
  const { get, set } = useUrlState();
  const logResult = get("logResult");
  const selectedLogId = get("logId");
  const tab = get("tab") || "routes";

  const [editingRoute, setEditingRoute] = useState<ModelRouteListItem | null>(null);
  const [maxCost, setMaxCost] = useState("");
  const [allowlistText, setAllowlistText] = useState("");
  const [commandError, setCommandError] = useState<unknown>(null);
  const [testResults, setTestResults] = useState<Record<string, ConnectionTestResult>>({});

  const routesQuery = useQuery({
    queryKey: queryKeys.modelRoutes,
    queryFn: () => api.get<ListEnvelope<ModelRouteListItem>>("API-196", "/api/v1/model-routes"),
  });

  const logsQuery = useQuery({
    queryKey: queryKeys.aiInvocationLogs({ result: logResult }),
    queryFn: () =>
      api.get<ListEnvelope<AIInvocationLogListItem>>("API-184", "/api/v1/ai-invocation-logs", {
        result: logResult || undefined,
      }),
  });

  const logDetailQuery = useQuery({
    queryKey: queryKeys.aiInvocationLog(selectedLogId || "none"),
    queryFn: () =>
      api.get<ResourceEnvelope<AIInvocationLogListItem>>(
        "API-185",
        `/api/v1/ai-invocation-logs/${selectedLogId}`,
      ),
    enabled: Boolean(selectedLogId),
  });

  const routes = routesQuery.data?.data.items ?? [];
  const logs = logsQuery.data?.data.items ?? [];

  const saveRoute = useMutation({
    mutationFn: (route: ModelRouteListItem) =>
      api.put<ResourceEnvelope<ModelRouteListItem>>(
        "API-197",
        `/api/v1/model-routes/${route.id}`,
        {
          expected_version: route.version,
          task_type: route.task_type,
          data_classification: route.data_classification,
          provider_allowlist: allowlistText
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
          max_cost: Number(maxCost),
          fallback: route.fallback ?? null,
          require_prompt_version: route.require_prompt_version,
          require_structured_output: route.require_structured_output,
          credential_bound: route.credential_present,
        },
      ),
    onMutate: () => setCommandError(null),
    onSuccess: () => {
      setEditingRoute(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.modelRoutes });
    },
    onError: (error) => setCommandError(error),
  });

  const testConnection = useMutation({
    mutationFn: (route: ModelRouteListItem) =>
      api.post<ResourceEnvelope<ConnectionTestResult>>(
        "API-198",
        `/api/v1/model-routes/${route.id}/connection-tests`,
        { expected_version: route.version },
      ),
    onMutate: () => setCommandError(null),
    onSuccess: (response, route) => {
      setTestResults((prev) => ({ ...prev, [route.id]: response.data }));
    },
    onError: (error) => setCommandError(error),
  });

  function openEdit(route: ModelRouteListItem) {
    setEditingRoute(route);
    setMaxCost(String(route.max_cost));
    setAllowlistText(route.provider_allowlist.join(", "));
    setCommandError(null);
  }

  return (
    <>
      <PageHeader title="模型路由配置" description="路由表 · 数据分级约束 · 连接测试 · AI 调用日志" />
      <Tabs value={tab} onValueChange={(value) => set({ tab: value })}>
        <TabsList>
          <TabsTrigger value="routes">路由表</TabsTrigger>
          <TabsTrigger value="logs">调用日志</TabsTrigger>
        </TabsList>

        <TabsContent value="routes" className="flex flex-col gap-4">
          <QueryGate isPending={routesQuery.isPending} error={routesQuery.error} apis={PAGE_APIS.P22}>
            {routes.length === 0 ? (
              <EmptyState title="无模型路由" />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>任务类型</TableHead>
                    <TableHead>数据分级</TableHead>
                    <TableHead>Provider 白名单</TableHead>
                    <TableHead>成本上限</TableHead>
                    <TableHead>凭证</TableHead>
                    <TableHead>版本</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {routes.map((route) => {
                    const testResult = testResults[route.id];
                    return (
                      <TableRow key={route.id}>
                        <TableCell className="font-mono text-xs">{route.task_type}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{route.data_classification}</Badge>
                          {route.data_classification === "Restricted" ? (
                            <p className="mt-1 text-xs text-warning">Restricted 默认不出站</p>
                          ) : null}
                        </TableCell>
                        <TableCell className="text-xs">{route.provider_allowlist.join(", ") || "—"}</TableCell>
                        <TableCell className="font-mono text-xs">{route.max_cost}</TableCell>
                        <TableCell className="text-xs">
                          {route.credential_present ? "已绑定" : "未绑定"}
                        </TableCell>
                        <TableCell className="font-mono text-xs">{route.version}</TableCell>
                        <TableCell className="space-y-1 text-right">
                          <MutateOnly>
                            <div className="flex justify-end gap-2">
                              <Button size="sm" variant="outline" onClick={() => openEdit(route)}>
                                编辑
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={testConnection.isPending}
                                onClick={() => testConnection.mutate(route)}
                              >
                                测试连接
                              </Button>
                            </div>
                          </MutateOnly>
                          {testResult ? (
                            <p className="text-xs text-muted-foreground">
                              {testResult.reachable ? "可达" : "不可达"} · {testResult.latency_ms}ms
                              {testResult.error_class ? ` · ${testResult.error_class}` : ""}
                            </p>
                          ) : null}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </QueryGate>

          {editingRoute ? (
            <div className="rounded-lg border p-4">
              <h2 className="mb-3 text-sm font-medium">编辑路由 · {editingRoute.task_type}</h2>
              <div className="grid max-w-lg gap-3">
                <div className="grid gap-1">
                  <Label htmlFor="max-cost">成本上限</Label>
                  <Input
                    id="max-cost"
                    value={maxCost}
                    onChange={(event) => setMaxCost(event.target.value)}
                  />
                </div>
                <div className="grid gap-1">
                  <Label htmlFor="allowlist">Provider 白名单（逗号分隔）</Label>
                  <Input
                    id="allowlist"
                    value={allowlistText}
                    onChange={(event) => setAllowlistText(event.target.value)}
                  />
                </div>
                <div className="flex gap-2">
                  <MutateOnly>
                    <Button
                      size="sm"
                      disabled={saveRoute.isPending}
                      onClick={() => editingRoute && saveRoute.mutate(editingRoute)}
                    >
                      保存
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setEditingRoute(null)}>
                      取消
                    </Button>
                  </MutateOnly>
                </div>
              </div>
            </div>
          ) : null}
        </TabsContent>

        <TabsContent value="logs" className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            <Input
              placeholder="result: ok | degraded | refused"
              value={logResult}
              onChange={(event) => set({ logResult: event.target.value, logId: undefined })}
              className="max-w-xs"
            />
          </div>
          <QueryGate isPending={logsQuery.isPending} error={logsQuery.error} apis={PAGE_APIS.P22}>
            {logs.length === 0 ? (
              <EmptyState title="无调用日志" />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>时间</TableHead>
                    <TableHead>模型</TableHead>
                    <TableHead>Prompt 版本</TableHead>
                    <TableHead>分级</TableHead>
                    <TableHead>结果</TableHead>
                    <TableHead>延迟</TableHead>
                    <TableHead>成本</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {logs.map((log) => (
                    <TableRow
                      key={log.id}
                      className="cursor-pointer"
                      data-selected={log.id === selectedLogId}
                      onClick={() => set({ logId: log.id })}
                    >
                      <TableCell className="font-mono text-xs">{log.created_at}</TableCell>
                      <TableCell className="font-mono text-xs">{log.model}</TableCell>
                      <TableCell className="font-mono text-xs">{log.prompt_version}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{log.data_classification}</Badge>
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={log.result} />
                      </TableCell>
                      <TableCell className="font-mono text-xs">{log.latency_ms}ms</TableCell>
                      <TableCell className="font-mono text-xs">{log.cost}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </QueryGate>

          {selectedLogId ? (
            <QueryGate
              isPending={logDetailQuery.isPending}
              error={logDetailQuery.error}
              apis={PAGE_APIS.P22}
            >
              {logDetailQuery.data ? (
                <Alert>
                  <AlertTitle>日志详情 · {logDetailQuery.data.data.id}</AlertTitle>
                  <AlertDescription className="font-mono text-xs">
                    model={logDetailQuery.data.data.model} · prompt_version=
                    {logDetailQuery.data.data.prompt_version} · usage=
                    {JSON.stringify(logDetailQuery.data.data.usage)} · result=
                    {logDetailQuery.data.data.result}
                  </AlertDescription>
                </Alert>
              ) : null}
            </QueryGate>
          ) : null}
        </TabsContent>
      </Tabs>

      <CommandFeedback error={commandError} apis={PAGE_APIS.P22} action="路由命令" />
    </>
  );
}
