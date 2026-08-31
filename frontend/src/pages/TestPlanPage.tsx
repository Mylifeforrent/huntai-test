import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ListEnvelope } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { useUrlState } from "@/hooks/useUrlState";

export function TestPlanPage() {
  const { projectId = "" } = useParams();
  const { get, set } = useUrlState();
  const q = get("q");
  const cursor = get("cursor");

  const query = useQuery({
    queryKey: queryKeys.testPlans({ projectId, q, cursor }),
    queryFn: () =>
      api.get<ListEnvelope<Record<string, unknown>>>("API-050", "/api/v1/test-plans", {
        project_id: projectId,
        q: q || undefined,
        cursor: cursor || undefined,
      }),
    enabled: Boolean(projectId),
  });
  const items = query.data?.data.items ?? [];

  return (
    <>
      <PageHeader
        title="测试计划"
        description="计划编排（关联 Jira fixVersion）· 用例集选择 · 执行历史与计划级报告 · 定时回归绑定"
      />
      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="按名称筛选"
          value={q}
          onChange={(event) => set({ q: event.target.value, cursor: undefined })}
          className="max-w-56"
        />
      </div>
      <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P06}>
        {items.length === 0 ? (
          <EmptyState title="无测试计划" hint="空集是 200 + items: []，与请求失败不同" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>计划</TableHead>
                <TableHead>fixVersion</TableHead>
                <TableHead>用例数</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item, index) => {
                const id = String(item.id ?? index);
                return (
                  <TableRow key={id}>
                    <TableCell>
                      <p className="font-medium">{String(item.name ?? id)}</p>
                      <p className="font-mono text-xs text-muted-foreground">{id}</p>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{String(item.jira_fix_version ?? "—")}</TableCell>
                    <TableCell className="font-mono">{String(item.case_count ?? "—")}</TableCell>
                    <TableCell>
                      <Button size="sm" asChild>
                        <Link to="/test-center/kickoff">执行</Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </QueryGate>
    </>
  );
}
