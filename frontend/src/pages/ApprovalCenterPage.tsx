import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type {
  ActionPreview,
  ActionPreviewRequest,
  ApprovalRequestDetail,
  ApprovalRequestListItem,
  ApprovalResubmissionResult,
  ListEnvelope,
  ResourceEnvelope,
} from "@/api/types";
import {
  APPROVAL_PERSPECTIVES,
  APPROVAL_STATUSES,
  PREVIEW_ACTION_TYPES,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CommandFeedback, EmptyState, MutateOnly, PageHeader, QueryGate } from "@/components/domain/PageState";
import { ApprovalCard, approvalCardFromRequest, type ApprovalCardModel } from "@/components/domain/ApprovalCard";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { useUrlState } from "@/hooks/useUrlState";
import { useSession } from "@/hooks/useSession";
import { asRecord } from "@/lib/utils";

const DEFAULT_PAYLOAD = '{\n  "summary": "preview from P10"\n}';

const QUEUE_APIS = PAGE_APIS.P10;

export function ApprovalCenterPage() {
  const { get, set } = useUrlState();
  const tab = get("tab") || "preview";
  const [commandError, setCommandError] = useState<unknown>(null);
  const [previewResult, setPreviewResult] = useState<ActionPreview | null>(null);

  const [actionType, setActionType] = useState<ActionPreviewRequest["action_type"]>("jira_write");
  const [projectId, setProjectId] = useState("");
  const [targetObjectType, setTargetObjectType] = useState("failure_cluster");
  const [targetObjectId, setTargetObjectId] = useState("");
  const [payloadText, setPayloadText] = useState(DEFAULT_PAYLOAD);

  const preview = useMutation({
    mutationFn: async () => {
      let payload: Record<string, unknown>;
      try {
        payload = JSON.parse(payloadText) as Record<string, unknown>;
        if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
          throw new Error("payload must be a JSON object");
        }
      } catch {
        throw new Error("payload 必须是合法 JSON 对象");
      }
      const body: ActionPreviewRequest = {
        action_type: actionType,
        target_object_type: targetObjectType.trim(),
        target_object_id: targetObjectId.trim(),
        payload,
      };
      if (projectId.trim()) {
        body.project_id = projectId.trim();
      }
      return api.post<ResourceEnvelope<ActionPreview>>(
        "API-120",
        "/api/v1/action-previews",
        body,
      );
    },
    onMutate: () => {
      setCommandError(null);
      setPreviewResult(null);
    },
    onSuccess: (response) => {
      setPreviewResult(response.data);
    },
    onError: (error) => {
      setCommandError(error);
    },
  });

  const previewCard: ApprovalCardModel | null = useMemo(() => {
    if (!previewResult) {
      return null;
    }
    const synthetic = {
      id: previewResult.approval_request_id ?? previewResult.preview_id,
      action_type: previewResult.action_type,
      status: previewResult.gate === "REQUIRE_APPROVAL" ? "PENDING" : previewResult.gate,
      side_effect_level: previewResult.side_effect_level,
      card_payload: previewResult.card_payload,
      param_hash: previewResult.param_hash,
      target_object_id: previewResult.target.object_id,
    };
    return approvalCardFromRequest(asRecord(synthetic));
  }, [previewResult]);

  return (
    <>
      <PageHeader
        title="审批中心"
        description="Preview（API-120）与待处理队列分区。九要素卡片由服务端组装；禁止客户端生成 param_hash。"
      />
      <Tabs value={tab} onValueChange={(value) => set({ tab: value })}>
        <TabsList>
          <TabsTrigger value="preview">Policy Gate Preview</TabsTrigger>
          <TabsTrigger value="queue">待处理队列</TabsTrigger>
        </TabsList>
        <TabsContent value="preview" className="mt-4 flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>发起 Preview（API-120）</CardTitle>
              <CardDescription>
                L2+ 动作经四值 Gate 裁决；L3+ 过期会话返回 HT-AUTH-002 后须 API-004 再重放。
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="preview-action">action_type</Label>
                  <Select
                    value={actionType}
                    onValueChange={(value) =>
                      setActionType(value as ActionPreviewRequest["action_type"])
                    }
                  >
                    <SelectTrigger id="preview-action">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PREVIEW_ACTION_TYPES.map((item) => (
                        <SelectItem key={item} value={item}>
                          {item}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="preview-project">project_id（项目级动作必填）</Label>
                  <Input
                    id="preview-project"
                    value={projectId}
                    onChange={(event) => setProjectId(event.target.value)}
                    placeholder="UUID"
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="preview-target-type">target_object_type</Label>
                  <Input
                    id="preview-target-type"
                    value={targetObjectType}
                    onChange={(event) => setTargetObjectType(event.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="preview-target-id">target_object_id</Label>
                  <Input
                    id="preview-target-id"
                    value={targetObjectId}
                    onChange={(event) => setTargetObjectId(event.target.value)}
                    placeholder="UUID"
                  />
                </div>
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="preview-payload">payload（JSON）</Label>
                <Textarea
                  id="preview-payload"
                  className="min-h-28 font-mono text-xs"
                  value={payloadText}
                  onChange={(event) => setPayloadText(event.target.value)}
                />
              </div>
              <MutateOnly>
                <Button
                  disabled={preview.isPending || !targetObjectId.trim() || !targetObjectType.trim()}
                  onClick={() => preview.mutate()}
                >
                  {preview.isPending ? "受理中…" : "提交 Preview"}
                </Button>
              </MutateOnly>
              <CommandFeedback error={commandError} apis={PAGE_APIS.P10_preview} action="API-120 Preview" />
            </CardContent>
          </Card>
          {previewResult ? (
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-muted-foreground">gate</span>
                <StatusBadge status={previewResult.gate} />
                <span className="font-mono text-xs text-muted-foreground">
                  param_hash: {previewResult.param_hash}
                </span>
              </div>
              {previewCard ? (
                <ApprovalCard card={previewCard} undeveloped />
              ) : null}
            </div>
          ) : null}
        </TabsContent>
        <TabsContent value="queue" className="mt-4">
          <ApprovalQueuePanel />
        </TabsContent>
      </Tabs>
    </>
  );
}

function ApprovalQueuePanel() {
  const { get, set } = useUrlState();
  const session = useSession();
  const queryClient = useQueryClient();
  const [commandError, setCommandError] = useState<unknown>(null);
  const [resubmitHint, setResubmitHint] = useState<string | null>(null);

  const statusFilter = get("status") || "";
  const actionFilter = get("action_type") || "";
  const perspective = get("perspective") || "inbox";
  const selectedId = get("id") || "";

  const listQuery = useQuery({
    queryKey: queryKeys.approvals({ status: statusFilter, action_type: actionFilter, perspective }),
    queryFn: () =>
      api.get<ListEnvelope<ApprovalRequestListItem>>("API-110", "/api/v1/approval-requests", {
        status: statusFilter || undefined,
        action_type: actionFilter || undefined,
        perspective,
      }),
    enabled: session.phase === "ready",
  });

  const items = listQuery.data?.data.items ?? [];

  const detailQuery = useQuery({
    queryKey: queryKeys.approval(selectedId),
    queryFn: () =>
      api.get<ResourceEnvelope<ApprovalRequestDetail>>(
        "API-111",
        `/api/v1/approval-requests/${selectedId}`,
      ),
    enabled: Boolean(selectedId) && session.phase === "ready",
  });

  const selectedItem = useMemo(() => {
    if (detailQuery.data?.data) {
      return detailQuery.data.data;
    }
    return items.find((item) => item.id === selectedId);
  }, [detailQuery.data, items, selectedId]);

  const card: ApprovalCardModel | null = useMemo(() => {
    if (!selectedItem) {
      return null;
    }
    return approvalCardFromRequest(
      asRecord(selectedItem),
      session.me?.user.id,
    );
  }, [selectedItem, session.me?.user.id]);

  const invalidateQueue = async () => {
    await queryClient.invalidateQueries({ queryKey: ["approval-requests"] });
    if (selectedId) {
      await queryClient.invalidateQueries({ queryKey: queryKeys.approval(selectedId) });
    }
  };

  const decisionMutation = useMutation({
    mutationFn: async (input: { decision: "approve" | "reject"; reason?: string }) => {
      if (!selectedItem) {
        throw new Error("未选择审批项");
      }
      return api.post<ResourceEnvelope<ApprovalRequestListItem>>(
        "API-112",
        `/api/v1/approval-requests/${selectedItem.id}/decisions`,
        {
          decision: input.decision,
          reason: input.reason,
          expected_version: selectedItem.version,
        },
      );
    },
    onMutate: () => setCommandError(null),
    onSuccess: async () => {
      await invalidateQueue();
    },
    onError: (error) => setCommandError(error),
  });

  const resubmitMutation = useMutation({
    mutationFn: async () => {
      if (!selectedItem) {
        throw new Error("未选择审批项");
      }
      const payload = detailQuery.data?.data.action_payload_redacted;
      if (!payload || Object.keys(payload).length === 0) {
        throw new Error("缺少 action_payload_redacted，无法重新提交");
      }
      return api.post<ResourceEnvelope<ApprovalResubmissionResult>>(
        "API-113",
        `/api/v1/approval-requests/${selectedItem.id}/resubmissions`,
        { payload },
      );
    },
    onMutate: () => {
      setCommandError(null);
      setResubmitHint(null);
    },
    onSuccess: async (response) => {
      const newId = response.data.new_approval_request.id;
      set({ id: newId });
      await invalidateQueue();
    },
    onError: (error) => {
      if (error instanceof Error && error.message.includes("action_payload_redacted")) {
        setResubmitHint("详情未返回 action_payload_redacted，请从 Preview 重新发起。");
      }
      setCommandError(error);
    },
  });

  const isViewerOnly =
    session.me?.memberships.length &&
    session.me.memberships.every((membership) => membership.role === "viewer");

  return (
    <div className="flex flex-col gap-4 lg:grid lg:grid-cols-[minmax(16rem,22rem)_1fr]">
      <Card>
        <CardHeader>
          <CardTitle>审批队列</CardTitle>
          <CardDescription>筛选条件写入 URL；列表来自 API-110。</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-col gap-2">
            <Label htmlFor="queue-perspective">perspective</Label>
            <Select value={perspective} onValueChange={(value) => set({ perspective: value, id: "" })}>
              <SelectTrigger id="queue-perspective">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {APPROVAL_PERSPECTIVES.map((item) => (
                  <SelectItem key={item} value={item}>
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="queue-status">status</Label>
            <Select
              value={statusFilter || "__all__"}
              onValueChange={(value) => set({ status: value === "__all__" ? "" : value, id: "" })}
            >
              <SelectTrigger id="queue-status">
                <SelectValue placeholder="全部" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">全部</SelectItem>
                {APPROVAL_STATUSES.map((item) => (
                  <SelectItem key={item} value={item}>
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="queue-action">action_type</Label>
            <Select
              value={actionFilter || "__all__"}
              onValueChange={(value) => set({ action_type: value === "__all__" ? "" : value, id: "" })}
            >
              <SelectTrigger id="queue-action">
                <SelectValue placeholder="全部" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">全部</SelectItem>
                {PREVIEW_ACTION_TYPES.map((item) => (
                  <SelectItem key={item} value={item}>
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <QueryGate isPending={listQuery.isPending} error={listQuery.error} apis={QUEUE_APIS}>
            {items.length === 0 ? (
              <EmptyState title="队列为空" hint="无匹配审批请求，或当前视角下无可处理项。" compact />
            ) : (
              <ul className="flex flex-col gap-1">
                {items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={`w-full rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                        selectedId === item.id ? "border-primary bg-muted" : "hover:bg-muted/60"
                      }`}
                      onClick={() => set({ id: item.id })}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate font-medium">{item.action_type}</span>
                        <StatusBadge status={item.status} />
                      </div>
                      <p className="truncate font-mono text-xs text-muted-foreground">{item.id}</p>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </QueryGate>
        </CardContent>
      </Card>
      <div className="flex flex-col gap-3">
        {isViewerOnly ? (
          <EmptyState title="只读视角" hint="viewer 可查看队列但不可批准或重新提交。" compact />
        ) : null}
        {selectedItem && card ? (
          <>
            <ApprovalCard
              card={card}
              busy={decisionMutation.isPending || resubmitMutation.isPending}
              onApprove={() => decisionMutation.mutate({ decision: "approve" })}
              onReject={(reason) => decisionMutation.mutate({ decision: "reject", reason })}
              onResubmit={() => resubmitMutation.mutate()}
            />
            <CommandFeedback error={commandError} apis={QUEUE_APIS} action="审批决策" />
            {resubmitHint ? <p className="text-xs text-muted-foreground">{resubmitHint}</p> : null}
          </>
        ) : (
          <EmptyState title="选择审批项" hint="从左侧列表选择一条记录查看九要素卡片。" />
        )}
      </div>
    </div>
  );
}
