import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ActionPreview, EvidencePreview, ListEnvelope, ResourceEnvelope } from "@/api/types";
import { useSession } from "@/hooks/useSession";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { MutateOnly, PageHeader, QueryGate, EmptyState, CommandFeedback } from "@/components/domain/PageState";
import { EvidenceViewer } from "@/components/domain/EvidenceViewer";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { UndevelopedCallout } from "@/components/domain/UndevelopedCallout";

type LocatorFixPreview = {
  field: string;
  current: string;
  suggested: string;
  reason: string;
  confidence: number;
};

export function CaseDetailPage() {
  const { caseId = "" } = useParams();
  const navigate = useNavigate();
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
  const role = membership?.role;
  const canApply = role === "owner" || role === "admin" || role === "tester";
  const canRollback = role === "owner" || role === "admin";
  const lifecycle = String(data.lifecycle_status ?? "");
  const isActive = lifecycle === "ACTIVE";

  const caseType = String(data.case_type ?? "");
  const isWeb = caseType === "web";
  const steps = Array.isArray(data.steps) ? data.steps : [];
  const locators = Array.isArray(data.locator_health) ? data.locator_health : [];
  const evidence = (data.evidence_preview ?? {
    screenshot_artifact_ids: [],
    video_artifact_ids: [],
    trace_artifact_ids: [],
  }) as EvidencePreview;
  const versionItems = versions.data?.data.items ?? [];
  const caseVersion = typeof data.version === "number" ? data.version : null;
  const rollbackTargetId = versionItems
    .map((item) => asRecord(item))
    .find((item) => item.is_current !== true && typeof item.id === "string")?.id;
  const rollbackTarget =
    typeof rollbackTargetId === "string" ? rollbackTargetId : "";
  const clusterConfidence =
    typeof data.locator_stale_cluster_confidence === "number" ? data.locator_stale_cluster_confidence : null;

  const healCandidate = locators.find((item) => {
    const row = asRecord(item);
    const preview = asRecord(row.fix_preview);
    return typeof preview.confidence === "number" && preview.confidence >= 0.7;
  });
  const healRow = healCandidate ? asRecord(healCandidate) : null;
  const healPreview = healRow ? asRecord(healRow.fix_preview) : null;
  const failureClusterId =
    typeof healRow?.failure_cluster_id === "string" ? healRow.failure_cluster_id : "";
  const fixConfidence = typeof healPreview?.confidence === "number" ? healPreview.confidence : 0;
  const canShowApply =
    canApply &&
    isActive &&
    fixConfidence >= 0.7 &&
    (clusterConfidence === null || clusterConfidence >= 0.7) &&
    Boolean(healPreview?.suggested);

  const degradedLocator = locators.find((item) => {
    const row = asRecord(item);
    return Boolean(row.human_repair_hint) || Boolean(row.dom_diff);
  });
  const degradedRow = degradedLocator ? asRecord(degradedLocator) : null;

  const rollback = useMutation({
    mutationFn: () => {
      if (caseVersion === null || !rollbackTarget) {
        throw new Error("缺少可回滚的历史版本");
      }
      return api.post<ResourceEnvelope<Record<string, unknown>>>(
        "API-039",
        `/api/v1/test-cases/${caseId}/rollback`,
        {
          expected_version: caseVersion,
          target_version_id: rollbackTarget,
          reason: "heal rollback",
        },
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.testCase(caseId) });
      void queryClient.invalidateQueries({ queryKey: ["test-cases", caseId, "versions"] });
    },
  });

  const healApply = useMutation({
    mutationFn: async () => {
      if (!healPreview || !failureClusterId || caseVersion === null) {
        throw new Error("缺少自愈修复上下文");
      }
      const patch = parseSuggestedPatch(String(healPreview.suggested ?? ""));
      return api.post<ResourceEnvelope<ActionPreview>>("API-120", "/api/v1/action-previews", {
        action_type: "heal_apply",
        project_id: projectId,
        target_object_type: "test_case",
        target_object_id: caseId,
        expected_target_version: caseVersion,
        payload: {
          failure_cluster_id: failureClusterId,
          cluster_confidence: clusterConfidence,
          fix_confidence: fixConfidence,
          patch,
        },
      });
    },
    onSuccess: (payload) => {
      if (payload.data.gate === "REQUIRE_APPROVAL") {
        navigate("/approvals");
      }
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
                        <TableHead>表达式</TableHead>
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
                            <TableCell className="font-mono text-xs">
                              {String(row.expression ?? row.locator_id ?? "")}
                            </TableCell>
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
                <CardTitle>A3 定位器建议 / Diff</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                {healPreview ? (
                  <LocatorHealDiff preview={normalizeFixPreview(healPreview)} />
                ) : degradedRow ? (
                  <div className="space-y-2 text-sm">
                    {typeof degradedRow.human_repair_hint === "string" ? (
                      <p>
                        <span className="font-medium">人工修复提示：</span>
                        {degradedRow.human_repair_hint}
                      </p>
                    ) : null}
                    {typeof degradedRow.dom_diff === "string" ? (
                      <pre className="overflow-auto rounded-md bg-muted p-3 font-mono text-xs">
                        {degradedRow.dom_diff}
                      </pre>
                    ) : null}
                  </div>
                ) : (
                  <EmptyState title="暂无 A3 建议" />
                )}
                {canShowApply ? (
                  <MutateOnly>
                    <Button size="sm" disabled={healApply.isPending} onClick={() => healApply.mutate()}>
                      可应用（API-120 heal_apply）
                    </Button>
                  </MutateOnly>
                ) : null}
                <CommandFeedback error={healApply.error} apis={PAGE_APIS.P13} action="heal_apply Preview（API-120）" />
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
                  screenshotArtifactId={evidence.screenshot_artifact_ids[0]}
                  videoArtifactId={evidence.video_artifact_ids[0]}
                  traceArtifactId={evidence.trace_artifact_ids[0]}
                />
              </CardContent>
            </Card>
          </>
        ) : null}
        <Card>
          <CardHeader className="flex-row items-center justify-between gap-2">
            <CardTitle>版本历史</CardTitle>
            {canRollback && rollbackTarget ? (
              <MutateOnly>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={rollback.isPending}
                  onClick={() => rollback.mutate()}
                >
                  回滚到上一版本（API-039）
                </Button>
              </MutateOnly>
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

function LocatorHealDiff({ preview }: { preview: LocatorFixPreview }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>字段</TableHead>
          <TableHead>当前</TableHead>
          <TableHead>建议</TableHead>
          <TableHead>原因</TableHead>
          <TableHead>置信度</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableRow>
          <TableCell>{preview.field}</TableCell>
          <TableCell className="font-mono text-xs">{preview.current}</TableCell>
          <TableCell className="max-w-xs truncate font-mono text-xs">{preview.suggested}</TableCell>
          <TableCell>{preview.reason}</TableCell>
          <TableCell>{preview.confidence}</TableCell>
        </TableRow>
      </TableBody>
    </Table>
  );
}

function normalizeFixPreview(raw: Record<string, unknown>): LocatorFixPreview {
  return {
    field: String(raw.field ?? ""),
    current: String(raw.current ?? ""),
    suggested: String(raw.suggested ?? ""),
    reason: String(raw.reason ?? ""),
    confidence: typeof raw.confidence === "number" ? raw.confidence : 0,
  };
}

function parseSuggestedPatch(suggested: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(suggested) as unknown;
    if (typeof parsed === "object" && parsed !== null) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return {};
  }
  return {};
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}
