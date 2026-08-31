import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import type { ActionPreview, ActionPreviewRequest, ResourceEnvelope } from "@/api/types";
import { PREVIEW_ACTION_TYPES } from "@/api/types";
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
import { CommandFeedback, PageHeader } from "@/components/domain/PageState";
import { ApprovalCard, approvalCardFromRequest, type ApprovalCardModel } from "@/components/domain/ApprovalCard";
import { UndevelopedCallout } from "@/components/domain/UndevelopedCallout";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { useUrlState } from "@/hooks/useUrlState";
import { asRecord } from "@/lib/utils";

const DEFAULT_PAYLOAD = '{\n  "summary": "preview from P10"\n}';

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
              <div className="grid gap-4 md:grid-cols-2">
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
              <Button
                disabled={preview.isPending || !targetObjectId.trim() || !targetObjectType.trim()}
                onClick={() => preview.mutate()}
              >
                {preview.isPending ? "受理中…" : "提交 Preview"}
              </Button>
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
          <UndevelopedCallout apis={PAGE_APIS.P10} action="待处理审批队列（API-110/112/113）" />
        </TabsContent>
      </Tabs>
    </>
  );
}
