import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ListEnvelope } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { useUrlState } from "@/hooks/useUrlState";

export function GateEvalHistoryPage() {
  const { get, set } = useUrlState();
  const projectId = get("projectId");
  const result = get("result");
  const testRunId = get("testRunId");
  const cursor = get("cursor");

  const query = useQuery({
    queryKey: queryKeys.gateEvaluations({ projectId, result, testRunId, cursor }),
    queryFn: () =>
      api.get<ListEnvelope<Record<string, unknown>>>("API-144", "/api/v1/gate-evaluations", {
        project_id: projectId || undefined,
        result: result || undefined,
        test_run_id: testRunId || undefined,
        cursor: cursor || undefined,
      }),
  });
  const items = query.data?.data.items ?? [];

  return (
    <>
      <PageHeader
        title="门禁评估历史"
        description="Check Run 关联 · 评估明细 · 豁免记录"
        actions={
          <Button variant="link" asChild>
            <Link to="/gates/policies">← 门禁策略</Link>
          </Button>
        }
      />
      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="projectId"
          value={projectId}
          onChange={(event) => set({ projectId: event.target.value, cursor: undefined })}
          className="max-w-56"
        />
        <Input
          placeholder="result（pass/fail/waived）"
          value={result}
          onChange={(event) => set({ result: event.target.value, cursor: undefined })}
          className="max-w-48"
        />
        <Input
          placeholder="testRunId"
          value={testRunId}
          onChange={(event) => set({ testRunId: event.target.value, cursor: undefined })}
          className="max-w-56"
        />
      </div>
      <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P12}>
        {items.length === 0 ? (
          <EmptyState title="无评估历史" hint="无评估的 run 不出现在本列表" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>评估 ID</TableHead>
                <TableHead>TestRun</TableHead>
                <TableHead>结论</TableHead>
                <TableHead>Check Run</TableHead>
                <TableHead>豁免</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item, index) => {
                const id = String(item.id ?? index);
                const runId = String(item.test_run_id ?? "");
                const check = asRecord(item.check_run_ref);
                return (
                  <TableRow key={id}>
                    <TableCell className="font-mono text-xs">{id}</TableCell>
                    <TableCell>
                      {runId ? (
                        <Link className="font-mono text-xs text-primary" to={`/test-center/runs/${runId}`}>
                          {runId}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={String(item.result ?? "")} />
                    </TableCell>
                    <TableCell className="text-xs">{String(check.status ?? check.state ?? "—")}</TableCell>
                    <TableCell className="font-mono text-xs">{String(item.waiver_approval_id ?? "—")}</TableCell>
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

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}
