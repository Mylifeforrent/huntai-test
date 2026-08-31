import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const LABELS: Record<string, string> = {
  PENDING: "待处理",
  VALIDATING: "校验中",
  RUNNING: "执行中",
  WAITING_EXTERNAL: "等待外部",
  WAITING_APPROVAL: "等待审批",
  STOPPING: "终止中",
  SUCCEEDED: "成功",
  FAILED: "失败",
  CANCELLED: "已取消",
  TIMEOUT: "超时",
  DRAFT: "草稿",
  PENDING_REVIEW: "待评审",
  ACTIVE: "活跃",
  DEPRECATED: "已废弃",
  CREATED: "已创建",
  APPROVED: "已批准",
  EXECUTED: "已执行",
  REJECTED: "已拒绝",
  EXPIRED: "已过期",
  PENDING_APPROVAL: "待审批",
  DEGRADED: "降级",
  DISABLED: "已禁用",
  PENDING_CONFIRM: "待确认",
  SUBMITTED: "已提交",
  READY: "就绪",
  FAILED_RETRYABLE: "失败可重试",
  pass: "通过",
  fail: "未通过",
  waived: "已豁免",
  script: "Script",
  agent: "Agent",
  external_ci: "外部 CI",
  valid: "有效",
  invalid: "失效",
};

const TONE: Record<string, string> = {
  PENDING: "bg-muted text-muted-foreground",
  VALIDATING: "bg-info-foreground text-info border-info/20",
  RUNNING: "bg-success-foreground text-success border-success/20",
  WAITING_EXTERNAL: "bg-warning-foreground text-warning border-warning/20",
  WAITING_APPROVAL: "bg-accent text-accent-foreground border-primary/20",
  STOPPING: "bg-warning-foreground text-warning border-warning/20",
  SUCCEEDED: "bg-success-foreground text-success border-success/20",
  FAILED: "bg-destructive/10 text-destructive border-destructive/20",
  CANCELLED: "bg-muted text-muted-foreground",
  TIMEOUT: "bg-destructive/10 text-destructive border-destructive/20",
  DRAFT: "bg-muted text-muted-foreground",
  PENDING_REVIEW: "bg-warning-foreground text-warning border-warning/20",
  ACTIVE: "bg-success-foreground text-success border-success/20",
  DEPRECATED: "bg-muted text-muted-foreground",
  CREATED: "bg-muted text-muted-foreground",
  APPROVED: "bg-success-foreground text-success border-success/20",
  EXECUTED: "bg-info-foreground text-info border-info/20",
  REJECTED: "bg-destructive/10 text-destructive border-destructive/20",
  EXPIRED: "bg-warning-foreground text-warning border-warning/20",
  PENDING_APPROVAL: "bg-warning-foreground text-warning border-warning/20",
  DEGRADED: "bg-warning-foreground text-warning border-warning/20",
  DISABLED: "bg-destructive/10 text-destructive border-destructive/20",
  PENDING_CONFIRM: "bg-warning-foreground text-warning border-warning/20",
  SUBMITTED: "bg-info-foreground text-info border-info/20",
  READY: "bg-success-foreground text-success border-success/20",
  FAILED_RETRYABLE: "bg-destructive/10 text-destructive border-destructive/20",
  pass: "bg-success-foreground text-success border-success/20",
  fail: "bg-destructive/10 text-destructive border-destructive/20",
  waived: "bg-accent text-accent-foreground",
  script: "bg-info-foreground text-info border-info/20",
  agent: "bg-accent text-accent-foreground",
  external_ci: "bg-warning-foreground text-warning border-warning/20",
  valid: "bg-success-foreground text-success border-success/20",
  invalid: "bg-destructive/10 text-destructive border-destructive/20",
};

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  return (
    <Badge variant="outline" className={cn(TONE[status], className)}>
      {LABELS[status] ?? status}
    </Badge>
  );
}
