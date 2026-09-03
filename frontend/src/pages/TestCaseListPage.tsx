import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ListEnvelope } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, QueryGate, EmptyState, CommandFeedback } from "@/components/domain/PageState";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { UndevelopedCallout } from "@/components/domain/UndevelopedCallout";
import { useUrlState } from "@/hooks/useUrlState";
import { useSession } from "@/hooks/useSession";
import { useState } from "react";

export function TestCaseListPage() {
  const { projectId = "" } = useParams();
  const { get, set } = useUrlState();
  const { me } = useSession();
  const queryClient = useQueryClient();
  const [ioTried, setIoTried] = useState(false);
  const [commandError, setCommandError] = useState<unknown>(null);
  const tag = get("tag");
  const validity = get("validity");
  const lifecycle = get("lifecycle");

  const membership = me?.memberships.find((row) => row.project_id === projectId);
  const canReview = membership?.role === "owner" || membership?.role === "admin";

  const query = useQuery({
    queryKey: queryKeys.testCases({ projectId, tag, validity, lifecycle }),
    queryFn: () =>
      api.get<ListEnvelope<Record<string, unknown>>>("API-030", "/api/v1/test-cases", {
        project_id: projectId,
        tags: tag || undefined,
        validity: validity || undefined,
        lifecycle_status: lifecycle || undefined,
      }),
  });

  const submitReview = useMutation({
    mutationFn: ({ caseId, version }: { caseId: string; version: number }) =>
      api.post("API-034", `/api/v1/test-cases/${caseId}/submit-review`, {
        expected_version: version,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.testCases({ projectId, tag, validity, lifecycle }) });
    },
    onError: (error) => setCommandError(error),
  });

  const reviewCase = useMutation({
    mutationFn: ({
      caseId,
      version,
      decision,
    }: {
      caseId: string;
      version: number;
      decision: "approve" | "reject";
    }) =>
      api.post("API-035", `/api/v1/test-cases/${caseId}/review`, {
        expected_version: version,
        decision,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.testCases({ projectId, tag, validity, lifecycle }) });
    },
    onError: (error) => setCommandError(error),
  });

  const items = query.data?.data.items ?? [];

  return (
    <>
      <PageHeader
        title="用例库"
        description="标签筛选含 ai-generated；validity=invalid 不可执行。导入导出走 API-200/202。"
        actions={
          <div className="flex gap-2">
            <Button variant="outline" asChild>
              <Link to={`/projects/${projectId}/cases/generation-review`}>生成审阅</Link>
            </Button>
            <Button variant="outline" onClick={() => setIoTried(true)}>
              Excel 导入
            </Button>
            <Button variant="outline" onClick={() => setIoTried(true)}>
              导出
            </Button>
          </div>
        }
      />
      <div className="flex flex-wrap gap-2">
        <Input placeholder="tags，如 ai-generated" value={tag} onChange={(e) => set({ tag: e.target.value })} className="max-w-48" />
        <Input placeholder="validity" value={validity} onChange={(e) => set({ validity: e.target.value })} className="max-w-36" />
        <Input placeholder="lifecycle" value={lifecycle} onChange={(e) => set({ lifecycle: e.target.value })} className="max-w-40" />
      </div>
      {ioTried ? <UndevelopedCallout apis={PAGE_APIS.P05} action="导入/导出" /> : null}
      <CommandFeedback error={commandError} apis={PAGE_APIS.P05} action="用例命令" />
      <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P05}>
        {items.length === 0 ? (
          <EmptyState title="无用例" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>用例</TableHead>
                <TableHead>生命周期</TableHead>
                <TableHead>有效性</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item, index) => {
                const id = String(item.id ?? index);
                const invalid = item.validity === "invalid";
                const lifecycleStatus = String(item.lifecycle_status ?? "");
                const version = Number(item.version ?? 1);
                return (
                  <TableRow key={id}>
                    <TableCell>
                      <Link to={`/projects/${projectId}/cases/${id}`} className="text-primary">
                        {String(item.title ?? id)}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={lifecycleStatus} />
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={String(item.validity ?? "valid")} />
                    </TableCell>
                    <TableCell className="space-x-2">
                      {lifecycleStatus === "DRAFT" ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => submitReview.mutate({ caseId: id, version })}
                        >
                          提交评审
                        </Button>
                      ) : null}
                      {lifecycleStatus === "PENDING_REVIEW" && canReview ? (
                        <>
                          <Button
                            size="sm"
                            onClick={() => reviewCase.mutate({ caseId: id, version, decision: "approve" })}
                          >
                            通过
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => reviewCase.mutate({ caseId: id, version, decision: "reject" })}
                          >
                            驳回
                          </Button>
                        </>
                      ) : null}
                      {invalid ? (
                        <span className="text-xs text-destructive">失效用例不可执行</span>
                      ) : (
                        <Button size="sm" asChild>
                          <Link to={`/test-center/kickoff?projectId=${projectId}&caseId=${id}`}>发起执行</Link>
                        </Button>
                      )}
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
