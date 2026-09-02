import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ResourceEnvelope } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PageHeader, QueryGate, EmptyState, CommandFeedback } from "@/components/domain/PageState";
import { useUrlState } from "@/hooks/useUrlState";
import { cn } from "@/lib/utils";

type SourceType = "openapi" | "postman" | "curl";

type DraftCase = Record<string, unknown>;

export function GenerationReviewPage() {
  const navigate = useNavigate();
  const { projectId = "" } = useParams();
  const queryClient = useQueryClient();
  const { get, set } = useUrlState();
  const generationId = get("generationId");
  const [source, setSource] = useState("");
  const [sourceType, setSourceType] = useState<SourceType>("openapi");
  const [selected, setSelected] = useState(0);
  const [editedJson, setEditedJson] = useState("");
  const [localCases, setLocalCases] = useState<DraftCase[]>([]);
  const [commandError, setCommandError] = useState<unknown>(null);

  const org = useQuery({
    queryKey: queryKeys.organization,
    queryFn: () => api.get<ResourceEnvelope<Record<string, unknown>>>("API-010", "/api/v1/organizations/current"),
  });

  const generationStatus = useQuery({
    queryKey: queryKeys.generation(generationId ?? ""),
    queryFn: () =>
      api.get<ResourceEnvelope<Record<string, unknown>>>(
        "API-181",
        `/api/v1/ai/generations/${generationId}`,
      ),
    enabled: Boolean(generationId),
    refetchInterval: (query) => {
      const status = String(query.state.data?.data.status ?? "");
      if (["succeeded", "partial", "failed"].includes(status)) return false;
      return 500;
    },
  });

  const drafts = useQuery({
    queryKey: queryKeys.generationDrafts(generationId ?? ""),
    queryFn: () =>
      api.get<ResourceEnvelope<Record<string, unknown>>>(
        "API-182",
        `/api/v1/ai/generations/${generationId}/drafts`,
      ),
    enabled: Boolean(generationId) && ["succeeded", "partial"].includes(String(generationStatus.data?.data.status ?? "")),
  });

  const controls = asRecord(org.data?.data.capability_controls);
  const tightened = Array.isArray(controls.tightened_capabilities)
    ? controls.tightened_capabilities.map(String)
    : [];
  const a1Disabled = controls.ai_global_tightened === true || tightened.includes("A1");

  const generationState = String(generationStatus.data?.data.status ?? "");
  const draftsReady = ["succeeded", "partial"].includes(generationState);
  const generationFailed = generationState === "failed";
  const bundle = drafts.data?.data ?? {};
  const failedItems = Array.isArray(bundle.failed_items) ? bundle.failed_items : [];
  const degraded = bundle.degraded === true || generationStatus.data?.data.degraded === true;
  const cases = localCases.length > 0 ? localCases : Array.isArray(bundle.cases) ? (bundle.cases as DraftCase[]) : [];
  const draftsPending = draftsReady && drafts.isPending;

  useEffect(() => {
    if (Array.isArray(bundle.cases) && bundle.cases.length > 0 && localCases.length === 0) {
      setLocalCases(bundle.cases as DraftCase[]);
      setSelected(0);
    }
  }, [bundle.cases, localCases.length]);

  const selectedCase = useMemo(() => cases[selected] ?? {}, [cases, selected]);

  useEffect(() => {
    setEditedJson(JSON.stringify(selectedCase, null, 2));
  }, [selectedCase]);

  const startGeneration = useMutation({
    mutationFn: () =>
      api.post<ResourceEnvelope<{ generation_id?: string }>>("API-180", "/api/v1/ai/generations", {
        project_id: projectId,
        source_type: sourceType,
        inline_content: source,
      }),
    onSuccess: (receipt) => {
      const id = String(asRecord(receipt.data).generation_id ?? "");
      if (id) {
        set({ generationId: id });
        setLocalCases([]);
        void queryClient.invalidateQueries({ queryKey: queryKeys.generation(id) });
      }
    },
    onError: (error) => setCommandError(error),
  });

  const adoptCase = useMutation({
    mutationFn: (draft: DraftCase) => {
      const title = String(draft.name ?? draft.title ?? "未命名用例");
      return api.post<ResourceEnvelope<Record<string, unknown>>>("API-032", "/api/v1/test-cases", {
        project_id: projectId,
        case_type: "api",
        execution_mode: "script",
        title,
        generation_id: generationId,
        drafts: [draft],
      });
    },
    onSuccess: () => {
      void navigate(`/projects/${projectId}/cases`);
    },
    onError: (error) => setCommandError(error),
  });

  function applyEdit() {
    try {
      const parsed = JSON.parse(editedJson) as DraftCase;
      setLocalCases((prev) => prev.map((item, index) => (index === selected ? parsed : item)));
    } catch {
      setCommandError(new Error("JSON 格式无效"));
    }
  }

  function discardCase() {
    setLocalCases((prev) => prev.filter((_, index) => index !== selected));
    setSelected(0);
  }

  function handleAdopt() {
    try {
      const draft = JSON.parse(editedJson) as DraftCase;
      adoptCase.mutate(draft);
    } catch {
      setCommandError(new Error("JSON 格式无效"));
    }
  }

  return (
    <>
      <PageHeader
        title="生成审阅"
        description="左：OpenAPI / Postman / curl 原文；右：结构化草稿；采纳 / 编辑 / 弃用"
      />
      {a1Disabled ? (
        <Alert variant="warning">
          <AlertTitle>A1 入口已禁用</AlertTitle>
          <AlertDescription>AI 降级或 A1 关停期间不可发起生成。导入本身不受影响。</AlertDescription>
        </Alert>
      ) : null}
      {degraded ? (
        <Alert variant="warning">
          <AlertTitle>AI 降级模式</AlertTitle>
          <AlertDescription>本次生成在降级模式下完成，请人工复核草稿。</AlertDescription>
        </Alert>
      ) : null}
      <CommandFeedback error={commandError} apis={PAGE_APIS.P07} action="A1 生成与采纳" />
      <div className="grid min-h-[28rem] grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="flex flex-col">
          <CardHeader>
            <CardTitle>源（OpenAPI / Postman / curl）</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col gap-3">
            <Select value={sourceType} onValueChange={(value) => setSourceType(value as SourceType)}>
              <SelectTrigger>
                <SelectValue placeholder="source_type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="openapi">openapi</SelectItem>
                <SelectItem value="postman">postman</SelectItem>
                <SelectItem value="curl">curl</SelectItem>
              </SelectContent>
            </Select>
            <Textarea
              className="min-h-64 font-mono text-xs"
              value={source}
              onChange={(event) => setSource(event.target.value)}
              placeholder="粘贴 OpenAPI / Postman / curl 原文…"
            />
            <Button
              onClick={() => startGeneration.mutate()}
              disabled={a1Disabled || !projectId || startGeneration.isPending}
            >
              {startGeneration.isPending ? "生成中…" : "发起 A1 生成"}
            </Button>
          </CardContent>
        </Card>
        <div className="flex flex-col gap-3">
          {generationId ? (
            <QueryGate
              isPending={generationStatus.isPending || draftsPending}
              error={generationStatus.error ?? drafts.error}
              apis={PAGE_APIS.P07}
            >
              {generationFailed ? (
                <Alert variant="destructive">
                  <AlertTitle>生成失败</AlertTitle>
                  <AlertDescription>
                    {String(asRecord(generationStatus.data?.data.error).message ?? "批次未产生可用草稿")}
                  </AlertDescription>
                </Alert>
              ) : (
                <DraftPane
                  cases={cases}
                  failedItems={failedItems}
                  selected={selected}
                  onSelect={setSelected}
                  selectedCase={selectedCase}
                  editedJson={editedJson}
                  onEditJson={setEditedJson}
                  onApplyEdit={applyEdit}
                  onAdopt={handleAdopt}
                  onDiscard={discardCase}
                  adoptPending={adoptCase.isPending}
                  running={["accepted", "running"].includes(generationState)}
                />
              )}
            </QueryGate>
          ) : (
            <EmptyState title="尚无草稿" hint="生成受理后由 API-181/182 返回结构化草稿与 failed_items。" />
          )}
        </div>
      </div>
    </>
  );
}

function DraftPane({
  cases,
  failedItems,
  selected,
  onSelect,
  selectedCase,
  editedJson,
  onEditJson,
  onApplyEdit,
  onAdopt,
  onDiscard,
  adoptPending,
  running,
}: {
  cases: DraftCase[];
  failedItems: unknown[];
  selected: number;
  onSelect: (index: number) => void;
  selectedCase: DraftCase;
  editedJson: string;
  onEditJson: (value: string) => void;
  onApplyEdit: () => void;
  onAdopt: () => void;
  onDiscard: () => void;
  adoptPending: boolean;
  running: boolean;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-[16rem_1fr]">
      <Card>
        <CardHeader>
          <CardTitle>结构化草稿</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {running ? <p className="text-sm text-muted-foreground">生成进行中，完成后展示草稿与失败列表。</p> : null}
          {cases.length === 0 && !running ? <p className="text-sm text-muted-foreground">无成功草稿</p> : null}
          {cases.map((item, index) => {
            const row = asRecord(item);
            return (
              <button
                key={String(row.name ?? index)}
                type="button"
                onClick={() => onSelect(index)}
                className={cn(
                  "rounded-md border p-2 text-left text-sm",
                  selected === index ? "border-primary bg-accent" : "",
                )}
              >
                {String(row.name ?? `草稿 ${index + 1}`)}
              </button>
            );
          })}
          <div className="rounded-md border border-destructive/30 bg-destructive/5 p-2">
            <p className="mb-1 text-xs font-medium text-destructive">生成失败（failed_items）</p>
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
              <Textarea
                className="min-h-48 font-mono text-xs"
                value={editedJson}
                onChange={(event) => onEditJson(event.target.value)}
              />
              <Alert>
                <AlertDescription>ai-generated 用例必须经人工评审，保存后为 DRAFT。</AlertDescription>
              </Alert>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={onAdopt} disabled={adoptPending}>
                  采纳
                </Button>
                <Button size="sm" variant="outline" onClick={onApplyEdit}>
                  应用编辑
                </Button>
                <Button size="sm" variant="destructive" onClick={onDiscard}>
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
