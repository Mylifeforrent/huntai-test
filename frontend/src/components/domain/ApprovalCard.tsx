import { useState, type ReactNode } from "react";
import { AlertTriangle, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { StatusBadge } from "./StatusBadge";
import { RiskBadge } from "./RiskBadge";
import { UndevelopedCallout } from "./UndevelopedCallout";
import { PAGE_APIS } from "@/api/catalog";
import { asRecord, formatServerScalar } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { useViewport } from "@/hooks/useViewport";

export interface ApprovalCardModel {
  id: string;
  action: string;
  target: string;
  status: string;
  risk: string;
  initiatorId?: string;
  currentUserId?: string;
  fourEyesSelf?: boolean;
  invalidated?: boolean;
  version?: number;
  diff?: Array<{ field: string; from: string; to: string }>;
  source?: string;
  model?: string;
  cost?: string;
  rollback?: string;
  paramHash?: string;
  originRequestId?: string;
}

export function approvalCardFromRequest(
  item: Record<string, unknown>,
  currentUserId?: string,
): ApprovalCardModel {
  const payload = asRecord(item.card_payload);
  const action = asRecord(payload.action);
  const resource = asRecord(payload.resource);
  const diff = asRecord(payload.diff);
  const dataSource = asRecord(payload.data_source);
  const model = asRecord(payload.model_and_skill_version);
  const risk = asRecord(payload.risk_level);
  const cost = asRecord(payload.cost_estimate);
  const rollback = asRecord(payload.rollback);
  const version = item.version;
  return {
    id: String(item.id ?? ""),
    action: String(action.summary ?? action.action_type ?? item.action_type ?? "—"),
    target: String(
      resource.display_name ?? resource.target_object_id ?? item.target_object_id ?? "—",
    ),
    status: String(item.status ?? "PENDING"),
    risk: String(risk.side_effect_level ?? item.side_effect_level ?? ""),
    initiatorId: typeof item.initiator_id === "string" ? item.initiator_id : undefined,
    currentUserId,
    fourEyesSelf: item.four_eyes_self === true,
    invalidated: item.expired_reason === "invalidated" || item.invalidated === true,
    version: typeof version === "number" ? version : undefined,
    diff: diffRows(diff),
    source: typeof dataSource.source_summary === "string" ? dataSource.source_summary : undefined,
    model: formatModel(model),
    cost: formatCost(cost),
    rollback: formatRollback(rollback),
    paramHash: typeof payload.param_hash === "string" ? payload.param_hash : typeof item.param_hash === "string" ? item.param_hash : undefined,
    originRequestId: typeof item.origin_request_id === "string" ? item.origin_request_id : undefined,
  };
}

export function ApprovalCard({
  card,
  onApprove,
  onReject,
  onResubmit,
  undeveloped,
  busy,
}: {
  card: ApprovalCardModel;
  onApprove?: () => void;
  onReject?: (reason: string) => void;
  onResubmit?: () => void;
  undeveloped?: boolean;
  busy?: boolean;
}) {
  const [hashOpen, setHashOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState("");
  const { canMutate } = useViewport();
  const selfApprove = Boolean(
    card.fourEyesSelf ||
      (card.initiatorId && card.currentUserId && card.initiatorId === card.currentUserId),
  );
  const actionsDisabled = card.invalidated || selfApprove || card.status !== "PENDING" || undeveloped || busy;

  return (
    <Card className="overflow-hidden" data-testid="approval-card">
      {card.invalidated ? (
        <div
          data-zone="invalid"
          className="flex items-center gap-2 bg-destructive px-4 py-2.5 text-sm font-medium text-destructive-foreground"
        >
          <AlertTriangle className="size-4 shrink-0" />
          审批已失效 — 参数已被修改，请走「修改后重新提交」
        </div>
      ) : null}
      <Section index="01" title="动作与目标资源" zone="1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs text-muted-foreground">{card.id}</span>
          <StatusBadge status={card.status} />
        </div>
        <p className="text-sm font-medium">{card.action}</p>
        <p className="text-sm text-muted-foreground">{card.target}</p>
      </Section>
      <Section index="02" title="前后 diff" zone="2">
        {card.diff?.length ? (
          <div className="flex flex-col gap-1 font-mono text-xs">
            {card.diff.map((row) => (
              <div key={row.field} className="grid grid-cols-[minmax(5rem,7rem)_1fr_1fr] gap-2">
                <span className="text-muted-foreground">{row.field}</span>
                <span className="rounded bg-destructive/10 px-2 py-1 text-destructive">{row.from}</span>
                <span className="rounded bg-success-foreground px-2 py-1 text-success">{row.to}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">无 diff 字段（后端未返回 card_payload）</p>
        )}
      </Section>
      <Section index="03" title="数据来源与模型 / Skill 版本" zone="3">
        <p className="font-mono text-xs">{card.source ?? "后端未返回"}</p>
        <p className="text-xs text-muted-foreground">{card.model ?? "后端未返回"}</p>
      </Section>
      <Section index="04" title="风险等级与成本估计" zone="4">
        <div className="flex items-center gap-4">
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-muted-foreground">风险</span>
            <RiskBadge level={card.risk} />
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-muted-foreground">成本估计</span>
            <span className="font-mono text-sm">{card.cost ?? "后端未返回"}</span>
          </div>
        </div>
      </Section>
      <Section index="05" title="回滚能力" zone="5">
        <p className="text-xs">{card.rollback ?? "无回滚能力必须声明（后端 card_payload）"}</p>
      </Section>
      <Section index="06" title="参数哈希" zone="6" last>
        <button
          type="button"
          className="flex items-center gap-1 text-xs text-primary"
          onClick={() => setHashOpen((open) => !open)}
        >
          <ChevronDown className={cn("size-3 transition-transform", hashOpen ? "rotate-180" : "")} />
          {hashOpen ? "折叠" : "展开核对"}
        </button>
        {hashOpen ? (
          <p className="rounded-md bg-sidebar px-3 py-2 font-mono text-xs break-all text-success-foreground">
            {card.paramHash ?? "后端未返回"}
          </p>
        ) : null}
        {card.originRequestId ? (
          <p className="text-xs text-muted-foreground">origin_request_id: {card.originRequestId}</p>
        ) : null}
      </Section>
      <div data-zone="actions" className="flex flex-col gap-3 bg-muted/40 px-4 py-3">
        {!canMutate ? (
          <p className="text-xs text-warning">当前为只读浏览，批准 / 拒绝请在宽度 ≥1024px 的桌面完成。</p>
        ) : null}
        {selfApprove ? <p className="text-xs text-warning">发起人本人不可批准（四眼前端呈现，服务端强制）。</p> : null}
        {undeveloped ? <UndevelopedCallout compact apis={PAGE_APIS.P10} action="批准 / 拒绝 / 重新提交" /> : null}
        {canMutate ? (
          <>
            <div className="flex flex-wrap gap-2">
              <Button disabled={actionsDisabled} onClick={onApprove}>
                批准
              </Button>
              <Button variant="destructive" disabled={actionsDisabled} onClick={() => setRejectOpen(true)}>
                拒绝（附理由）
              </Button>
              <Button variant="outline" disabled={undeveloped || busy} onClick={onResubmit}>
                修改后重新提交
              </Button>
            </div>
            {rejectOpen ? (
              <div className="flex flex-col gap-2">
                <Label htmlFor={`reject-${card.id}`}>拒绝理由（必填）</Label>
                <Textarea
                  id={`reject-${card.id}`}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                />
                <Button
                  variant="destructive"
                  disabled={!reason.trim() || undeveloped || busy}
                  onClick={() => onReject?.(reason)}
                >
                  确认拒绝
                </Button>
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </Card>
  );
}

function Section({
  index,
  title,
  children,
  last,
  zone,
}: {
  index: string;
  title: string;
  children: ReactNode;
  last?: boolean;
  zone: string;
}) {
  return (
    <section data-zone={zone} className={cn("flex flex-col gap-2 px-4 py-3", last ? "" : "border-b")}>
      <h3 className="flex items-center gap-2 text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">
        <span className="font-mono text-primary">{index}</span>
        {title}
      </h3>
      {children}
    </section>
  );
}

function diffRows(diff: Record<string, unknown>): Array<{ field: string; from: string; to: string }> {
  const before = asRecord(diff.before);
  const after = asRecord(diff.after);
  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])];
  if (keys.length > 0) {
    return keys.map((field) => ({
      field,
      from: stringifyDiffValue(before[field]),
      to: stringifyDiffValue(after[field]),
    }));
  }
  if (typeof diff.summary === "string" && diff.summary) {
    return [{ field: "summary", from: "", to: diff.summary }];
  }
  return [];
}

function stringifyDiffValue(value: unknown): string {
  if (value == null) {
    return "(无)";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function formatModel(model: Record<string, unknown>): string | undefined {
  const parts = [model.model, model.prompt_version, model.skill_version_id]
    .map((part) => (typeof part === "string" ? part : undefined))
    .filter((part): part is string => Boolean(part));
  return parts.length > 0 ? parts.join(" · ") : undefined;
}

function formatCost(cost: Record<string, unknown>): string | undefined {
  const amount = formatServerScalar(cost.amount);
  const unit = typeof cost.unit === "string" ? cost.unit : "";
  if (amount) {
    return unit ? `${amount} ${unit}` : amount;
  }
  if (typeof cost.unknown_reason === "string" && cost.unknown_reason) {
    return cost.unknown_reason;
  }
  return undefined;
}

function formatRollback(rollback: Record<string, unknown>): string | undefined {
  if (rollback.capability === "none" || rollback.none_declared === true) {
    return typeof rollback.compensation_summary === "string" && rollback.compensation_summary
      ? rollback.compensation_summary
      : "无回滚能力必须声明";
  }
  const parts = [
    typeof rollback.capability === "string" ? rollback.capability : undefined,
    typeof rollback.snapshot_ref === "string" ? `snapshot_ref: ${rollback.snapshot_ref}` : undefined,
    typeof rollback.compensation_summary === "string" ? rollback.compensation_summary : undefined,
  ].filter((part): part is string => Boolean(part));
  return parts.length > 0 ? parts.join(" · ") : undefined;
}
