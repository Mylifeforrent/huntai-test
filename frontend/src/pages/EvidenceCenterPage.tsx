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

export function EvidenceCenterPage() {
  const { get, set } = useUrlState();
  const q = get("q");
  const cursor = get("cursor");
  const [exportTried, setExportTried] = useState(false);

  const query = useQuery({
    queryKey: queryKeys.evidence({ q, cursor }),
    queryFn: () =>
      api.get<ListEnvelope<Record<string, unknown>>>("API-026", "/api/v1/evidence-objects", {
        q: q || undefined,
        cursor: cursor || undefined,
      }),
  });
  const items = query.data?.data.items ?? [];

  function exportPackage() {
    setExportTried(true);
    void api.post("API-028", "/api/v1/evidence-objects/export-packages", { q: q || undefined }).catch(() => undefined);
  }

  return (
    <>
      <PageHeader
        title="证据中心"
        description="证据检索 · 证据包导出（ZIP/MD/JSON）"
        actions={
          <Button variant="outline" onClick={exportPackage}>
            导出证据包
          </Button>
        }
      />
      <Input
        placeholder="搜索 claim、来源对象、连接器…"
        value={q}
        onChange={(event) => set({ q: event.target.value, cursor: undefined })}
      />
      {exportTried ? <UndevelopedCallout apis={PAGE_APIS.P20} action="证据包导出 API-028" /> : null}
      <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P20}>
        {items.length === 0 ? (
          <EmptyState title="无证据记录" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>证据 ID</TableHead>
                <TableHead>结论 (claim)</TableHead>
                <TableHead>来源</TableHead>
                <TableHead>主体</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item, index) => {
                const source = asRecord(item.source_object);
                return (
                  <TableRow key={String(item.id ?? index)}>
                    <TableCell className="font-mono text-xs">{String(item.id ?? "")}</TableCell>
                    <TableCell>{String(item.claim ?? "")}</TableCell>
                    <TableCell className="font-mono text-xs">{String(source.connector ?? source.resource ?? "")}</TableCell>
                    <TableCell className="text-xs">
                      {String(item.subject_type ?? "")} {String(item.subject_id ?? "")}
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

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}
