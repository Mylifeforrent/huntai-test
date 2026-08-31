import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ListEnvelope } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { UndevelopedCallout } from "@/components/domain/UndevelopedCallout";
import { useUrlState } from "@/hooks/useUrlState";

export function AuditSearchPage() {
  const { get, set } = useUrlState();
  const q = get("q");
  const actor = get("actor");
  const resourceType = get("resourceType");
  const cursor = get("cursor");
  const [siemTried, setSiemTried] = useState(false);

  const query = useQuery({
    queryKey: queryKeys.audit({ q, actor, resourceType, cursor }),
    queryFn: () =>
      api.get<ListEnvelope<Record<string, unknown>>>("API-024", "/api/v1/audit-events", {
        q: q || undefined,
        actor_user_id: actor || undefined,
        resource_type: resourceType || undefined,
        cursor: cursor || undefined,
      }),
  });
  const items = query.data?.data.items ?? [];

  function saveSiem() {
    setSiemTried(true);
    void api.put("API-040", "/api/v1/organizations/current/siem-export", { enabled: true }).catch(() => undefined);
  }

  return (
    <>
      <PageHeader
        title="审计检索"
        description="全字段检索 · 外发 SIEM 配置"
        actions={
          <Button variant="outline" onClick={saveSiem}>
            外发 SIEM 配置
          </Button>
        }
      />
      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="检索 actor / action / target / approval.bound_hash"
          value={q}
          onChange={(event) => set({ q: event.target.value, cursor: undefined })}
          className="max-w-md"
        />
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
      </div>
      {siemTried ? <UndevelopedCallout apis={PAGE_APIS.P24} action="SIEM 外发 API-040" /> : null}
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
                <TableHead>时间</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item, index) => (
                <TableRow key={String(item.id ?? index)}>
                  <TableCell className="font-mono text-xs">{String(item.id ?? "")}</TableCell>
                  <TableCell className="text-xs">{String(item.actor_user_id ?? item.actor ?? "")}</TableCell>
                  <TableCell className="font-mono text-xs">{String(item.action ?? item.event_type ?? "")}</TableCell>
                  <TableCell className="text-xs">
                    {String(item.resource_type ?? "")} {String(item.resource_id ?? "")}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{String(item.created_at ?? "")}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </QueryGate>
    </>
  );
}
