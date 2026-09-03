import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ListEnvelope, ResourceEnvelope } from "@/api/types";
import { useSession } from "@/hooks/useSession";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, QueryGate, EmptyState, CommandFeedback } from "@/components/domain/PageState";
import { EvidenceViewer } from "@/components/domain/EvidenceViewer";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { UndevelopedCallout } from "@/components/domain/UndevelopedCallout";

export function CaseDetailPage() {
  const { caseId = "" } = useParams();
  const queryClient = useQueryClient();
  const session = useSession();

  const detail = useQuery({
    queryKey: queryKeys.testCase(caseId),
    queryFn: () => api.get<ResourceEnvelope<Record<string, unknown>>>("API-031", `/api/v1/test-cases/${caseId}`),
    enabled: Boolean(caseId),
  });
  const versions = useQuery({
    queryKey: ["test-cases", caseId, "versions"],
    queryFn: () =>
      api.get<ListEnvelope<Record<string, unknown>>>("API-037", `/api/v1/test-cases/${caseId}/versions`),
    enabled: Boolean(caseId),
  });

  const data = detail.data?.data ?? {};
  const projectId = typeof data.project_id === "string" ? data.project_id : "";
  const membership = session.me?.memberships.find((item) => item.project_id === projectId);
  const canRollback = membership?.role === "owner" || membership?.role === "admin";

  const caseType = String(data.case_type ?? "");
  const isWeb = caseType === "web";
  const steps = Array.isArray(data.steps) ? data.steps : [];
  const locators = Array.isArray(data.locator_health) ? data.locator_health : [];
  const evidence = asRecord(data.evidence_preview);
  const versionItems = versions.data?.data.items ?? [];
  const currentVersionId = typeof data.current_version_id === "string" ? data.current_version_id : "";
  const caseVersion = typeof data.version === "number" ? data.version : null;

  const rollback = useMutation({
    mutationFn: () => {
      if (caseVersion === null || !currentVersionId) {
        throw new Error("缺少版本指针");
      }
      return api.post<ResourceEnvelope<Record<string, unknown>>>(
        "API-039",
        `/api/v1/test-cases/${caseId}/rollback`,
        {
          expected_version: caseVersion,
          target_version_id: currentVersionId,
          reason: "heal rollback",
        },
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.testCase(caseId) });
    },
  });

  return (
    <>
      <PageHeader
        title={typeof data.title === "string" ? data.title : "Web 用例详情"}
        description="步骤编辑 · 证据三件套 · 定位器主备与健康度 · 版本历史"
      />
      <QueryGate isPending={detail.isPending} error={detail.error} apis={PAGE_APIS.P13}>
        {caseType && !isWeb ? (
          <Alert>
            <AlertTitle>G2：详情结构仅对 Web 定义</AlertTitle>
            <AlertDescription>
              当前 case_type={caseType}。§4.2 仅对 Web 域定义用例详情页；api / performance 型结构未定义，本页不假装完整编辑器。
            </AlertDescription>
          </Alert>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <StatusBadge status={String(data.lifecycle_status ?? "")} />
          <StatusBadge status={String(data.validity ?? "")} />
          <Badge variant="outline">{caseType || "—"}</Badge>
        </div>
        {isWeb || !caseType ? (
          <>
            <Card>
              <CardHeader>
                <CardTitle>步骤</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {steps.length === 0 ? <EmptyState title="无步骤" /> : null}
                {steps.map((item, index) => (
                  <pre key={index} className="overflow-auto rounded-md bg-muted p-3 font-mono text-xs">
                    {JSON.stringify(item, null, 2)}
                  </pre>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>定位器主备与健康度</CardTitle>
              </CardHeader>
              <CardContent>
                {locators.length === 0 ? (
                  <EmptyState title="无定位器投影" />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>定位器</TableHead>
                        <TableHead>策略</TableHead>
                        <TableHead>主/备</TableHead>
                        <TableHead>健康度</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {locators.map((item, index) => {
                        const row = asRecord(item);
                        return (
                          <TableRow key={String(row.locator_id ?? index)}>
                            <TableCell className="font-mono text-xs">{String(row.locator_id ?? "")}</TableCell>
                            <TableCell>{String(row.strategy ?? "")}</TableCell>
                            <TableCell>{row.is_primary === true ? "主" : "备"}</TableCell>
                            <TableCell>
                              <StatusBadge status={String(row.health ?? "")} />
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>证据三件套</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="mb-3 text-xs text-muted-foreground">
                  证据引用（artifact id）≠ 下载授权。截图/视频/Trace 须经制品代理，本页不把 object_key 当 URL。
                </p>
                <EvidenceViewer
                  traceAvailable={
                    Array.isArray(evidence.trace_artifact_ids) && evidence.trace_artifact_ids.length > 0
                  }
                />
              </CardContent>
            </Card>
          </>
        ) : null}
        <Card>
          <CardHeader className="flex-row items-center justify-between gap-2">
            <CardTitle>版本历史</CardTitle>
            {canRollback && currentVersionId ? (
              <Button
                size="sm"
                variant="outline"
                disabled={rollback.isPending}
                onClick={() => rollback.mutate()}
              >
                回滚到当前快照（API-039）
              </Button>
            ) : null}
          </CardHeader>
          <CardContent>
            <CommandFeedback error={rollback.error} apis={PAGE_APIS.P13} action="版本回滚 API-039" />
            {versions.error ? (
              <UndevelopedCallout apis={PAGE_APIS.P13} error={versions.error} action="版本历史 API-037" />
            ) : versionItems.length === 0 ? (
              <EmptyState title="无版本" />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>seq</TableHead>
                    <TableHead>当前</TableHead>
                    <TableHead>分级</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {versionItems.map((item, index) => (
                    <TableRow key={String(item.id ?? index)}>
                      <TableCell className="font-mono">{String(item.version_seq ?? "")}</TableCell>
                      <TableCell>{item.is_current === true ? "是" : ""}</TableCell>
                      <TableCell>{String(item.data_classification ?? "")}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </QueryGate>
    </>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}
