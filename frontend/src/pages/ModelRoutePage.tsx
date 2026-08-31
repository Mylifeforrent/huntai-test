import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ListEnvelope } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { UndevelopedCallout } from "@/components/domain/UndevelopedCallout";

export function ModelRoutePage() {
  const [testTried, setTestTried] = useState(false);

  const query = useQuery({
    queryKey: queryKeys.modelRoutes,
    queryFn: () => api.get<ListEnvelope<Record<string, unknown>>>("API-196", "/api/v1/model-routes"),
  });
  const items = query.data?.data.items ?? [];

  function testConnection(routeId: string) {
    setTestTried(true);
    void api.post("API-198", `/api/v1/model-routes/${routeId}/connection-tests`, {}).catch(() => undefined);
  }

  return (
    <>
      <PageHeader title="模型路由配置" description="路由表 · 数据分级约束 · 测试连接" />
      <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P22}>
        {items.length === 0 ? (
          <EmptyState title="无模型路由" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>任务类型</TableHead>
                <TableHead>数据分级</TableHead>
                <TableHead>Provider 白名单</TableHead>
                <TableHead>成本上限</TableHead>
                <TableHead>降级</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item, index) => {
                const id = String(item.id ?? index);
                const allowlist = Array.isArray(item.provider_allowlist) ? item.provider_allowlist.map(String) : [];
                const fallback = asRecord(item.fallback);
                return (
                  <TableRow key={id}>
                    <TableCell className="font-mono text-xs">{String(item.task_type ?? "")}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{String(item.data_classification ?? "")}</Badge>
                    </TableCell>
                    <TableCell className="text-xs">{allowlist.join(", ") || "—"}</TableCell>
                    <TableCell className="font-mono text-xs">{String(item.max_cost ?? "—")}</TableCell>
                    <TableCell className="font-mono text-xs text-warning">{String(fallback.strategy ?? fallback.mode ?? "—")}</TableCell>
                    <TableCell>
                      <Button size="sm" variant="outline" onClick={() => testConnection(id)}>
                        测试连接
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </QueryGate>
      {testTried ? <UndevelopedCallout apis={PAGE_APIS.P22} action="测试连接 API-198" /> : null}
    </>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}
