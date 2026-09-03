import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ListEnvelope, TestRunListItem } from "@/api/types";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { useUrlState } from "@/hooks/useUrlState";

export function TestRunListPage() {
  const { projectId } = useParams();
  const { get, set } = useUrlState();
  const status = get("status");
  const source = get("source");
  const cursor = get("cursor");

  const query = useQuery({
    queryKey: queryKeys.testRuns({ projectId: projectId ?? "", status, source, cursor }),
    queryFn: () =>
      api.get<ListEnvelope<TestRunListItem>>("API-060", "/api/v1/test-runs", {
        project_id: projectId,
        status: status || undefined,
        execution_source: source || undefined,
        cursor: cursor || undefined,
      }),
    enabled: Boolean(projectId),
  });

  const items = query.data?.data.items ?? [];

  return (
    <>
      <PageHeader
        title="TestRun 列表"
        description="WAITING_APPROVAL / WAITING_EXTERNAL 持续可见并展示滞留时长。筛选进入 URL。"
        actions={
          <Button asChild>
            <Link to={projectId ? `/test-center/kickoff?projectId=${projectId}` : "/test-center/kickoff"}>发起执行</Link>
          </Button>
        }
      />
      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="状态（PENDING/RUNNING/...）"
          value={status}
          onChange={(event) => set({ status: event.target.value, cursor: undefined })}
          className="max-w-56"
        />
        <Input
          placeholder="execution_source"
          value={source}
          onChange={(event) => set({ source: event.target.value, cursor: undefined })}
          className="max-w-48"
        />
      </div>
      <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P09}>
        {items.length === 0 ? (
          <EmptyState title="无 TestRun" hint="空集是 200 + items: []，与请求失败不同" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>来源</TableHead>
                <TableHead>滞留</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>
                    <Link className="font-mono text-primary" to={`/test-center/runs/${row.id}`}>
                      {row.id}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={row.status} />
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={row.execution_source} />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {row.status === "WAITING_APPROVAL" || row.status === "WAITING_EXTERNAL"
                      ? typeof row.dwell_seconds === "number"
                        ? `${row.dwell_seconds}s`
                        : "—"
                      : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </QueryGate>
    </>
  );
}
