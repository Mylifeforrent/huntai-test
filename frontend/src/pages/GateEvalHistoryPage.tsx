import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { useSession } from "@/hooks/useSession";

type GateEvalItem = {
  id: string;
  test_run_id: string;
  result: string;
  check_run_ref?: Record<string, unknown> | null;
  waiver_approval_id?: string | null;
};

export function GateEvalHistoryPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { get, set } = useUrlState();
  const session = useSession();
  const projectId = get("projectId");
  const result = get("result");
  const testRunId = get("testRunId");
  const cursor = get("cursor");
  const selectedId = get("evaluationId");

  const canWaiver =
    session.me?.memberships.some(
      (membership) =>
        membership.project_id === projectId &&
        (membership.role === "owner" || membership.role === "admin"),
    ) ?? false;

  const query = useQuery({
    queryKey: queryKeys.gateEvaluations({ projectId, result, testRunId, cursor }),
    queryFn: () =>
      api.get<ListEnvelope<GateEvalItem>>("API-144", "/api/v1/gate-evaluations", {
        project_id: projectId || undefined,
        result: result || undefined,
        test_run_id: testRunId || undefined,
        cursor: cursor || undefined,
      }),
    enabled: Boolean(projectId || testRunId),
  });
  const items = query.data?.data.items ?? [];

  const detailQuery = useQuery({
    queryKey: queryKeys.gateEvaluationDetail(selectedId),
    queryFn: () =>
      api.get<{ data: GateEvalItem & { threshold_details?: Record<string, unknown> } }>(
        "API-145",
        `/api/v1/gate-evaluations/${selectedId}`,
      ),
    enabled: Boolean(selectedId),
  });

  const waiverMutation = useMutation({
    mutationFn: async (evaluationId: string) => {
      const preview = await api.post<{ data: { approval_request_id?: string; gate?: string } }>(
        "API-120",
        "/api/v1/action-previews",
        {
          action_type: "gate_waiver",
          project_id: projectId,
          target_object_type: "gate_evaluation",
          target_object_id: evaluationId,
          payload: { confirm: true },
        },
      );
      if (preview.data.gate === "REQUIRE_APPROVAL" && preview.data.approval_request_id) {
        navigate(`/approvals?highlight=${preview.data.approval_request_id}`);
      }
      return preview;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.gateEvaluations({ projectId, result, testRunId, cursor }) });
      if (selectedId) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.gateEvaluationDetail(selectedId) });
      }
    },
  });

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
                <TableHead>操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => {
                const id = String(item.id);
                const runId = String(item.test_run_id ?? "");
                const check = asRecord(item.check_run_ref);
                const showWaiver = item.result === "fail" && canWaiver && !item.waiver_approval_id;
                return (
                  <TableRow
                    key={id}
                    className={selectedId === id ? "bg-muted/50" : undefined}
                    onClick={() => set({ evaluationId: id })}
                  >
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
                    <TableCell className="text-xs">{String(check.sync_status ?? check.status ?? "—")}</TableCell>
                    <TableCell className="font-mono text-xs">{String(item.waiver_approval_id ?? "—")}</TableCell>
                    <TableCell>
                      {showWaiver ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={(event) => {
                            event.stopPropagation();
                            waiverMutation.mutate(id);
                          }}
                          disabled={waiverMutation.isPending}
                        >
                          申请豁免
                        </Button>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </QueryGate>
      {selectedId && detailQuery.data?.data ? (
        <div className="mt-4 rounded-md border p-4 text-sm">
          <p className="font-medium">评估明细（API-145）</p>
          <pre className="mt-2 overflow-auto text-xs">
            {JSON.stringify(detailQuery.data.data.threshold_details ?? {}, null, 2)}
          </pre>
        </div>
      ) : null}
    </>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}
