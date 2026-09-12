import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type {
  AuditEventListItem,
  ListEnvelope,
  OrganizationCurrentProjection,
  ResourceEnvelope,
  SiemExportConfig,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CommandFeedback, MutateOnly, PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { useUrlState } from "@/hooks/useUrlState";

export function AuditSearchPage() {
  const queryClient = useQueryClient();
  const { get, set } = useUrlState();
  const actor = get("actor");
  const resourceType = get("resourceType");
  const approvalId = get("approvalId");
  const requestHash = get("requestHash");
  const cursor = get("cursor");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [siemEnabled, setSiemEnabled] = useState(false);
  const [connectorId, setConnectorId] = useState("");
  const [commandError, setCommandError] = useState<unknown>(null);

  const orgQuery = useQuery({
    queryKey: queryKeys.organization,
    queryFn: () =>
      api.get<ResourceEnvelope<OrganizationCurrentProjection>>(
        "API-010",
        "/api/v1/organizations/current",
      ),
  });
  const orgVersion = orgQuery.data?.data.version;

  const query = useQuery({
    queryKey: queryKeys.audit({ actor, resourceType, approvalId, requestHash, cursor }),
    queryFn: () =>
      api.get<ListEnvelope<AuditEventListItem>>("API-024", "/api/v1/audit-events", {
        actor_user_id: actor || undefined,
        resource_type: resourceType || undefined,
        approval_id: approvalId || undefined,
        request_hash: requestHash || undefined,
        cursor: cursor || undefined,
      }),
  });
  const items = query.data?.data.items ?? [];

  const detailQuery = useQuery({
    queryKey: [...queryKeys.audit({}), "detail", selectedId ?? ""],
    queryFn: () =>
      api.get<ResourceEnvelope<AuditEventListItem>>(
        "API-025",
        `/api/v1/audit-events/${selectedId}`,
      ),
    enabled: selectedId !== null,
  });

  const saveSiem = useMutation({
    mutationFn: () => {
      if (orgVersion === undefined) {
        return Promise.reject(new Error("missing org version"));
      }
      const body: Record<string, unknown> = {
        expected_version: orgVersion,
        enabled: siemEnabled,
      };
      if (siemEnabled && connectorId.trim()) {
        body.destination_connector_id = connectorId.trim();
      }
      return api.put<ResourceEnvelope<SiemExportConfig>>(
        "API-040",
        "/api/v1/organizations/current/siem-export",
        body,
      );
    },
    onMutate: () => setCommandError(null),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.organization });
      void queryClient.invalidateQueries({ queryKey: queryKeys.me });
    },
    onError: (error) => setCommandError(error),
  });

  return (
    <>
      <PageHeader title="审计检索" description="不可变审计事件检索 · SIEM 外发配置" />
      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="actor_user_id"
          value={actor}
          onChange={(event) => set({ actor: event.target.value, cursor: undefined })}
          className="max-w-56"
        />
        <Input
          placeholder="resource_type"
          value={resourceType}
          onChange={(event) => set({ resourceType: event.target.value, cursor: undefined })}
          className="max-w-48"
        />
        <Input
          placeholder="approval_id"
          value={approvalId}
          onChange={(event) => set({ approvalId: event.target.value, cursor: undefined })}
          className="max-w-56"
        />
        <Input
          placeholder="request_hash"
          value={requestHash}
          onChange={(event) => set({ requestHash: event.target.value, cursor: undefined })}
          className="max-w-56"
        />
      </div>
      <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P24}>
        {items.length === 0 ? (
          <EmptyState title="无审计事件" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>事件 ID</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>动作</TableHead>
                <TableHead>对象</TableHead>
                <TableHead>结果</TableHead>
                <TableHead>时间</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => (
                <TableRow
                  key={item.id}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => setSelectedId(item.id)}
                >
                  <TableCell className="font-mono text-xs">{item.id}</TableCell>
                  <TableCell className="text-xs">{item.actor_user_id ?? "—"}</TableCell>
                  <TableCell className="font-mono text-xs">{item.action ?? "—"}</TableCell>
                  <TableCell className="text-xs">
                    {item.resource_type ?? ""} {item.resource_id ?? ""}
                  </TableCell>
                  <TableCell className="text-xs">{item.result ?? "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{item.created_at}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </QueryGate>
      {selectedId && detailQuery.data?.data ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">审计详情</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 font-mono text-xs">
            <p>id: {detailQuery.data.data.id}</p>
            <p>action: {detailQuery.data.data.action ?? "—"}</p>
            <p>result: {detailQuery.data.data.result ?? "—"}</p>
            <p>request_hash: {detailQuery.data.data.request_hash ?? "—"}</p>
            <p>data_classification: {detailQuery.data.data.data_classification}</p>
          </CardContent>
        </Card>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">SIEM 外发配置</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <Checkbox
              id="siem-enabled"
              checked={siemEnabled}
              onCheckedChange={(checked) => setSiemEnabled(checked === true)}
            />
            <Label htmlFor="siem-enabled">启用外发</Label>
          </div>
          {siemEnabled ? (
            <Input
              placeholder="destination_connector_id（S-M0-12 前将返回 404）"
              value={connectorId}
              onChange={(event) => setConnectorId(event.target.value)}
              className="max-w-md"
            />
          ) : null}
          <MutateOnly>
            <Button
              variant="outline"
              disabled={saveSiem.isPending || orgVersion === undefined}
              onClick={() => saveSiem.mutate()}
            >
              保存 SIEM 配置
            </Button>
          </MutateOnly>
          <CommandFeedback error={commandError} apis={PAGE_APIS.P24} action="SIEM 外发 API-040" />
        </CardContent>
      </Card>
    </>
  );
}
