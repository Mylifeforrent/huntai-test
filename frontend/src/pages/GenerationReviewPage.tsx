import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ResourceEnvelope } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { UndevelopedCallout } from "@/components/domain/UndevelopedCallout";
import { useUrlState } from "@/hooks/useUrlState";
import { cn } from "@/lib/utils";

export function GenerationReviewPage() {
  const { projectId = "" } = useParams();
  const { get, set } = useUrlState();
  const generationId = get("generationId");
  const [source, setSource] = useState("");
  const [generateTried, setGenerateTried] = useState(false);
  const [draftTried, setDraftTried] = useState(false);
  const [selected, setSelected] = useState(0);

  const org = useQuery({
    queryKey: queryKeys.organization,
    queryFn: () => api.get<ResourceEnvelope<Record<string, unknown>>>("API-010", "/api/v1/organizations/current"),
  });
  const drafts = useQuery({
    queryKey: ["ai", "generations", generationId, "drafts"],
    queryFn: () =>
      api.get<ResourceEnvelope<Record<string, unknown>>>(
        "API-182",
        `/api/v1/ai/generations/${generationId}/drafts`,
      ),
    enabled: Boolean(generationId),
  });

  const controls = asRecord(org.data?.data.capability_controls);
  const tightened = Array.isArray(controls.tightened_capabilities)
    ? controls.tightened_capabilities.map(String)
    : [];
  const a1Disabled = controls.ai_global_tightened === true || tightened.includes("A1");

  const bundle = drafts.data?.data ?? {};
  const cases = Array.isArray(bundle.cases) ? bundle.cases : [];
  const failedItems = Array.isArray(bundle.failed_items) ? bundle.failed_items : [];
  const selectedCase = asRecord(cases[selected]);

  function startGeneration() {
    setGenerateTried(true);
    void api
      .post<ResourceEnvelope<{ generation_id?: string }> | { resource_id?: string }>(
        "API-180",
        "/api/v1/ai/generations",
        { project_id: projectId, source_type: "openapi", inline_content: source },
      )
      .then((receipt) => {
        const id =
          "resource_id" in receipt
            ? receipt.resource_id
            : asRecord(asRecord(receipt).data).generation_id;
        if (typeof id === "string" && id) set({ generationId: id });
      })
      .catch(() => undefined);
  }

  function markDraftAction() {
    setDraftTried(true);
    if (generationId) {
      void api.get("API-182", `/api/v1/ai/generations/${generationId}/drafts`).catch(() => undefined);
    }
  }

  return (
    <>
      <PageHeader
        title="生成审阅"
        description="左：OpenAPI 原文；右：结构化草稿；采纳 / 编辑 / 弃用；partial 失败可见"
      />
      {a1Disabled ? (
        <Alert variant="warning">
          <AlertTitle>A1 入口已禁用</AlertTitle>
          <AlertDescription>AI 降级或 A1 关停期间不可发起生成。导入本身不受影响。</AlertDescription>
        </Alert>
      ) : null}
      <div className="grid min-h-[28rem] grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="flex flex-col">
          <CardHeader>
            <CardTitle>源（OpenAPI / Postman / curl）</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col gap-3">
            <Textarea
              className="min-h-64 font-mono text-xs"
              value={source}
              onChange={(event) => setSource(event.target.value)}
              placeholder="粘贴 OpenAPI 原文…"
            />
            <Button onClick={startGeneration} disabled={a1Disabled || !projectId}>
              发起 A1 生成
            </Button>
          </CardContent>
        </Card>
        <div className="flex flex-col gap-3">
          {generationId ? (
            <QueryGate isPending={drafts.isPending} error={drafts.error} apis={PAGE_APIS.P07}>
              <DraftPane
                cases={cases}
                failedItems={failedItems}
                selected={selected}
                onSelect={setSelected}
                selectedCase={selectedCase}
                onAction={markDraftAction}
              />
            </QueryGate>
          ) : (
            <EmptyState title="尚无草稿" hint="生成受理后由 API-182 返回结构化草稿与 failed_items。" />
          )}
        </div>
      </div>
      {generateTried ? <UndevelopedCallout apis={PAGE_APIS.P07} action="A1 生成受理 API-180" /> : null}
      {draftTried ? <UndevelopedCallout apis={PAGE_APIS.P07} action="草稿采纳/编辑/弃用依赖 API-180/182" /> : null}
    </>
  );
}

function DraftPane({
  cases,
  failedItems,
  selected,
  onSelect,
  selectedCase,
  onAction,
}: {
  cases: unknown[];
  failedItems: unknown[];
  selected: number;
  onSelect: (index: number) => void;
  selectedCase: Record<string, unknown>;
  onAction: () => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-[16rem_1fr]">
      <Card>
        <CardHeader>
          <CardTitle>结构化草稿</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {cases.length === 0 ? <p className="text-sm text-muted-foreground">无成功草稿</p> : null}
          {cases.map((item, index) => {
            const row = asRecord(item);
            return (
              <button
                key={String(row.name ?? index)}
                type="button"
                onClick={() => onSelect(index)}
                className={cn("rounded-md border p-2 text-left text-sm", selected === index ? "border-primary bg-accent" : "")}
              >
                {String(row.name ?? `草稿 ${index + 1}`)}
              </button>
            );
          })}
          <div className="rounded-md border border-destructive/30 bg-destructive/5 p-2">
            <p className="mb-1 text-xs font-medium text-destructive">生成失败（failed_items，禁止静默丢弃）</p>
            {failedItems.length === 0 ? <p className="text-xs text-muted-foreground">无失败项</p> : null}
            {failedItems.map((item, index) => {
              const row = asRecord(item);
              return (
                <div key={index} className="text-xs text-destructive">
                  <span className="font-mono">{String(row.endpoint ?? "")}</span>
                  <p>{String(row.reason ?? "")}</p>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{String(selectedCase.name ?? "用例详情")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {cases.length === 0 ? (
            <EmptyState title="选择或等待草稿" />
          ) : (
            <>
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline">{String(selectedCase.case_type ?? "")}</Badge>
                <Badge variant="outline">{String(selectedCase.priority ?? "")}</Badge>
                <Badge variant="secondary">ai-generated</Badge>
              </div>
              <pre className="overflow-auto rounded-md bg-muted p-3 font-mono text-xs">
                {JSON.stringify({ steps: selectedCase.steps, assertions: selectedCase.assertions }, null, 2)}
              </pre>
              <Alert>
                <AlertDescription>ai-generated 用例必须经人工评审，禁止直接写入 ACTIVE。</AlertDescription>
              </Alert>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={onAction}>
                  采纳
                </Button>
                <Button size="sm" variant="outline" onClick={onAction}>
                  编辑
                </Button>
                <Button size="sm" variant="destructive" onClick={onAction}>
                  弃用
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}
