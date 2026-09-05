import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { newIdempotencyKey } from "@/api/apiConfig";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ListEnvelope, ResourceEnvelope } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { useUrlState } from "@/hooks/useUrlState";

interface EvidenceObjectItem {
  id: string;
  claim: string;
  source_object?: unknown;
  content_ref?: string | null;
  subject_type: string;
  subject_id: string;
  data_classification: string;
}

interface ExportReceipt {
  id: string;
  status: string;
  poll?: { sse_path?: string };
}

const EXPORT_FORMATS = ["zip", "md", "json"] as const;
type ExportFormat = (typeof EXPORT_FORMATS)[number];

const TERMINAL_RECEIPT_STATUSES = new Set(["succeeded", "failed", "partial"]);

export function EvidenceCenterPage() {
  const { get, set } = useUrlState();
  const subjectType = get("subject_type");
  const subjectId = get("subject_id");
  const createdFrom = get("created_from");
  const createdTo = get("created_to");
  const cursor = get("cursor");
  const [exportFormat, setExportFormat] = useState<ExportFormat>("zip");
  const [receipt, setReceipt] = useState<ExportReceipt | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [sseHint, setSseHint] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const subjectPair = subjectType !== "" && subjectId !== "";
  const listParams = {
    subject_type: subjectType,
    subject_id: subjectId,
    created_from: createdFrom,
    created_to: createdTo,
    cursor,
  };

  const query = useQuery({
    queryKey: queryKeys.evidence(listParams),
    queryFn: () =>
      api.get<ListEnvelope<EvidenceObjectItem>>("API-026", "/api/v1/evidence-objects", {
        subject_type: subjectType || undefined,
        subject_id: subjectId || undefined,
        created_from: createdFrom || undefined,
        created_to: createdTo || undefined,
        cursor: cursor || undefined,
      }),
  });
  const items = query.data?.data.items ?? [];

  const receiptId = receipt?.id;
  const receiptStatus = receipt?.status;
  const receiptQuery = useQuery({
    queryKey: ["command-receipt", receiptId],
    enabled:
      receiptId !== undefined &&
      receiptStatus !== undefined &&
      !TERMINAL_RECEIPT_STATUSES.has(receiptStatus),
    refetchInterval: 1500,
    queryFn: async () => {
      const data = await api.get<ResourceEnvelope<ExportReceipt>>(
        "API-071",
        `/api/v1/command-receipts/${receiptId ?? ""}`,
      );
      return data.data;
    },
  });

  const authoritativeStatus = receiptQuery.data?.status ?? receipt?.status ?? null;
  const refetchReceipt = receiptQuery.refetch;

  useEffect(() => {
    if (receiptQuery.data) {
      setReceipt((current) => (current && current.id === receiptQuery.data.id ? receiptQuery.data : current));
    }
  }, [receiptQuery.data]);

  // SSE 只推展示进度（非命令、非完成判定）；完成以回执 GET + API-223 为准。
  useEffect(() => {
    const ssePath = receipt?.poll?.sse_path;
    if (!ssePath || (authoritativeStatus !== null && TERMINAL_RECEIPT_STATUSES.has(authoritativeStatus))) {
      return;
    }
    const source = new EventSource(ssePath, { withCredentials: true });
    source.addEventListener("progress", (event) => {
      try {
        const parsed = JSON.parse((event as MessageEvent<string>).data) as { hint?: string };
        setSseHint(parsed.hint ?? null);
      } catch {
        setSseHint(null);
      }
    });
    source.addEventListener("resource_changed", () => {
      setSseHint("status_may_have_changed");
      void refetchReceipt();
    });
    eventSourceRef.current = source;
    return () => {
      source.close();
      eventSourceRef.current = null;
    };
  }, [receipt?.id, receipt?.poll?.sse_path, authoritativeStatus, refetchReceipt]);

  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
    };
  }, []);

  function updateFilter(next: Record<string, string | undefined>) {
    set({ ...next, cursor: undefined });
  }

  async function exportPackage() {
    setExportError(null);
    setExporting(true);
    try {
      const data = await api.post<ResourceEnvelope<ExportReceipt>>(
        "API-028",
        "/api/v1/evidence-objects/export-packages",
        {
          format: exportFormat,
          subject_type: subjectType || undefined,
          subject_id: subjectId || undefined,
        },
        newIdempotencyKey(),
      );
      setSseHint(null);
      setReceipt(data.data);
    } catch (cause) {
      setExportError(cause instanceof Error ? cause.message : "导出受理失败");
    } finally {
      setExporting(false);
    }
  }

  async function downloadPackage() {
    if (!receipt) return;
    setExportError(null);
    try {
      const blob = await api.getBlob("API-223", `/api/v1/export-packages/${receipt.id}/content`);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `evidence-package-${receipt.id}.${exportFormat}`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setExportError(cause instanceof Error ? cause.message : "导出包下载失败");
    }
  }

  return (
    <>
      <PageHeader
        title="证据中心"
        description="证据检索 · 证据包导出（ZIP/MD/JSON）"
      />
      <div className="mb-4 flex flex-wrap items-end gap-2">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground" htmlFor="evidence-subject-type">
            主体类型
          </label>
          <Select
            value={subjectType || "all"}
            onValueChange={(value) => updateFilter({ subject_type: value === "all" ? undefined : value })}
          >
            <SelectTrigger id="evidence-subject-type" className="w-40">
              <SelectValue placeholder="全部" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部</SelectItem>
              <SelectItem value="test_run">test_run</SelectItem>
              <SelectItem value="case_result">case_result</SelectItem>
              <SelectItem value="failure_cluster">failure_cluster</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground" htmlFor="evidence-subject-id">
            主体 ID
          </label>
          <Input
            id="evidence-subject-id"
            className="w-64"
            placeholder="UUID（与主体类型成对）"
            value={subjectId}
            onChange={(event) => updateFilter({ subject_id: event.target.value || undefined })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground" htmlFor="evidence-created-from">
            创建时间从
          </label>
          <Input
            id="evidence-created-from"
            className="w-56"
            placeholder="ISO-8601"
            value={createdFrom}
            onChange={(event) => updateFilter({ created_from: event.target.value || undefined })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground" htmlFor="evidence-created-to">
            创建时间到
          </label>
          <Input
            id="evidence-created-to"
            className="w-56"
            placeholder="ISO-8601"
            value={createdTo}
            onChange={(event) => updateFilter({ created_to: event.target.value || undefined })}
          />
        </div>
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border bg-muted/30 p-3">
        <Select value={exportFormat} onValueChange={(value) => setExportFormat(value as ExportFormat)}>
          <SelectTrigger className="w-28" aria-label="导出格式">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {EXPORT_FORMATS.map((format) => (
              <SelectItem key={format} value={format}>
                {format.toUpperCase()}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button onClick={() => void exportPackage()} disabled={!subjectPair || exporting}>
          导出证据包（当前主体筛选）
        </Button>
        {!subjectPair ? (
          <span className="text-xs text-muted-foreground">导出需先按「主体类型 + 主体 ID」筛选证据范围。</span>
        ) : null}
        {receipt ? (
          <div className="flex items-center gap-2">
            <Badge variant={authoritativeStatus === "succeeded" ? "default" : "secondary"}>
              {authoritativeStatus === "succeeded"
                ? "受理中 / 已完成，以可下载为准"
                : authoritativeStatus === "accepted" || authoritativeStatus === "running"
                  ? "受理中"
                  : `回执 ${authoritativeStatus}`}
            </Badge>
            {authoritativeStatus === "succeeded" ? (
              <Button variant="outline" onClick={() => void downloadPackage()}>
                下载导出包（API-223）
              </Button>
            ) : null}
          </div>
        ) : null}
        {sseHint ? <span className="text-xs text-muted-foreground">SSE 提示（非完成判定）：{sseHint}</span> : null}
        {exportError ? <span className="text-xs text-destructive">{exportError}</span> : null}
      </div>
      <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P20}>
        {items.length === 0 ? (
          <EmptyState title="无证据记录" />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>证据 ID</TableHead>
                  <TableHead>结论 (claim)</TableHead>
                  <TableHead>来源</TableHead>
                  <TableHead>主体</TableHead>
                  <TableHead>分级</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => {
                  const source = asRecord(item.source_object);
                  return (
                    <TableRow key={item.id}>
                      <TableCell className="font-mono text-xs">{item.id}</TableCell>
                      <TableCell>{item.claim}</TableCell>
                      <TableCell className="font-mono text-xs">
                        {String(source.connector ?? "")} · {String(source.resource ?? "")}
                      </TableCell>
                      <TableCell className="text-xs">
                        {item.subject_type} {item.subject_id}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{item.data_classification}</Badge>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            {query.data?.page.has_more && query.data.page.next_cursor ? (
              <div className="mt-3 flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => set({ cursor: query.data?.page.next_cursor ?? undefined })}
                >
                  下一页
                </Button>
                {cursor ? (
                  <Button variant="ghost" onClick={() => set({ cursor: undefined })}>
                    重置分页
                  </Button>
                ) : null}
              </div>
            ) : null}
          </>
        )}
      </QueryGate>
    </>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}
