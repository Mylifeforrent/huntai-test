import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ListEnvelope, MeProjection, ResourceEnvelope } from "@/api/types";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CommandFeedback, PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { ApprovalCard, approvalCardFromRequest, type ApprovalCardModel } from "@/components/domain/ApprovalCard";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { RiskBadge } from "@/components/domain/RiskBadge";
import { useUrlState } from "@/hooks/useUrlState";
import { asRecord } from "@/lib/utils";
import { cn } from "@/lib/utils";

export function ApprovalCenterPage() {
  const { get, set } = useUrlState();
  const selectedId = get("id");
  const actionType = get("action");
  const queryClient = useQueryClient();
  const [commandError, setCommandError] = useState<unknown>(null);
  const [resubmitHint, setResubmitHint] = useState("");

  const me = useQuery({
    queryKey: queryKeys.me,
    queryFn: () => api.get<ResourceEnvelope<MeProjection>>("API-005", "/api/v1/me"),
  });
  const query = useQuery({
    queryKey: queryKeys.approvals({ status: "PENDING", action: actionType }),
    queryFn: () =>
      api.get<ListEnvelope<Record<string, unknown>>>("API-110", "/api/v1/approval-requests", {
        status: "PENDING",
        action_type: actionType || undefined,
      }),
  });

  const items = query.data?.data.items ?? [];
  const currentUserId = me.data?.data.user.id;
  const selected = useMemo(() => {
    const match = items.find((item) => String(item.id) === selectedId);
    return match ?? items[0];
  }, [items, selectedId]);

  const card: ApprovalCardModel | null = selected
    ? approvalCardFromRequest(asRecord(selected), currentUserId)
    : null;

  const decide = useMutation({
    mutationFn: (input: { decision: "approve" | "reject"; reason?: string }) => {
      if (!card) {
        throw new Error("未选择审批卡片");
      }
      if (typeof card.version !== "number") {
        throw new Error("缺少 expected_version，无法提交审批决策");
      }
      return api.post("API-112", `/api/v1/approval-requests/${card.id}/decisions`, {
        decision: input.decision,
        reason: input.reason,
        expected_version: card.version,
      });
    },
    onMutate: () => {
      setCommandError(null);
      setResubmitHint("");
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["approval-requests"] });
    },
    onError: (error) => {
      setCommandError(error);
    },
  });

  const resubmit = useMutation({
    mutationFn: () => {
      if (!card) {
        throw new Error("未选择审批卡片");
      }
      const payload = asRecord(asRecord(selected).action_payload_redacted);
      if (Object.keys(payload).length === 0) {
        throw new Error("修改后重新提交需要完整执行参数（API-113 payload），当前卡片未返回可提交参数");
      }
      return api.post("API-113", `/api/v1/approval-requests/${card.id}/resubmissions`, {
        payload,
        expected_origin_version: card.version,
      });
    },
    onMutate: () => {
      setCommandError(null);
      setResubmitHint("");
    },
    onSuccess: () => {
      setResubmitHint("");
      void queryClient.invalidateQueries({ queryKey: ["approval-requests"] });
    },
    onError: (error) => {
      setCommandError(error);
    },
  });

  return (
    <>
      <PageHeader title="审批中心" description="九要素分区顺序冻结。批量队列处理同质卡片。" />
      <div className="flex gap-2">
        <Input
          placeholder="筛选动作类型"
          value={actionType}
          onChange={(event) => set({ action: event.target.value, id: undefined })}
          className="max-w-56"
        />
      </div>
      <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P10}>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[20rem_1fr]">
          <Card className="overflow-hidden">
            <CardHeader>
              <CardTitle>待处理队列</CardTitle>
              <CardDescription>{items.length} 条 PENDING · 选择一张打开右侧控制台</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-0 p-0">
              {items.length === 0 ? (
                <div className="p-4">
                  <EmptyState compact title="无待审批" hint="空集是 200 + items: []。" />
                </div>
              ) : null}
              {items.map((item) => {
                const row = asRecord(item);
                const payload = asRecord(row.card_payload);
                const risk = asRecord(payload.risk_level);
                const id = String(row.id ?? "");
                const active = card?.id === id;
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => set({ id })}
                    className={cn(
                      "flex flex-col gap-1 border-b px-4 py-3 text-left last:border-b-0",
                      active
                        ? "bg-accent shadow-[inset_2px_0_0_0_var(--color-primary)]"
                        : "hover:bg-muted/40",
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-muted-foreground">{id}</span>
                      <StatusBadge status={String(row.status ?? "")} />
                      <RiskBadge level={String(risk.side_effect_level ?? row.side_effect_level ?? "")} />
                    </div>
                    <p className="truncate text-sm">{String(row.action_type ?? "")}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {String(row.target_object_id ?? "")}
                    </p>
                  </button>
                );
              })}
            </CardContent>
          </Card>
          <div className="flex flex-col gap-3">
            {card ? (
              <ApprovalCard
                card={card}
                busy={decide.isPending || resubmit.isPending}
                onApprove={() => decide.mutate({ decision: "approve" })}
                onReject={(reason) => decide.mutate({ decision: "reject", reason })}
                onResubmit={() => {
                  const payload = asRecord(asRecord(selected).action_payload_redacted);
                  if (Object.keys(payload).length === 0) {
                    setCommandError(null);
                    setResubmitHint("修改后重新提交需要完整执行参数（API-113 payload）。当前响应未返回 action_payload_redacted，前端不伪造参数。");
                    return;
                  }
                  resubmit.mutate();
                }}
              />
            ) : (
              <EmptyState title="选择一张审批卡片" hint="队列为空时右侧保持空态，不伪造卡片。" />
            )}
            {resubmitHint ? <p className="text-xs text-warning">{resubmitHint}</p> : null}
            <CommandFeedback error={commandError} apis={PAGE_APIS.P10} action="审批决策 API-112 / 重新提交 API-113" />
          </div>
        </div>
      </QueryGate>
    </>
  );
}
