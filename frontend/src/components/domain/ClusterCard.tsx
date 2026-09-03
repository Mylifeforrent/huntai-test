import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { BlockingJudgment, ClusterCategory, FailureClusterFixPreview } from "@/api/types";
import { cn } from "@/lib/utils";

const CATEGORY_LABEL: Record<ClusterCategory, string> = {
  env_down: "环境故障",
  auth_expired: "认证过期",
  locator_stale: "定位器过期",
  assertion_real_bug: "真实缺陷",
  flaky: "不稳定测试",
  data_issue: "数据问题",
  unknown: "未知",
};

export interface ClusterCardModel {
  id: string;
  category: ClusterCategory | string;
  confidence: number;
  blocking: BlockingJudgment | string;
  evidenceHref?: string;
  summary?: string;
  ruleFallback?: boolean;
  canShowApply?: boolean;
  fixes?: FailureClusterFixPreview[];
}

export function ClusterCard({
  cluster,
  onCorrect,
  onApply,
  applyPending,
}: {
  cluster: ClusterCardModel;
  onCorrect?: (next: { category: string; blocking: string }) => void;
  onApply?: (fix: FailureClusterFixPreview) => void;
  applyPending?: boolean;
}) {
  const unknown = cluster.category === "unknown";
  const bestFix = (cluster.fixes ?? []).find((fix) => fix.confidence >= 0.7);
  const applyVisible = Boolean(
    cluster.canShowApply &&
      !cluster.ruleFallback &&
      cluster.confidence >= 0.7 &&
      bestFix,
  );

  return (
    <Card className={cn(unknown && "border-warning/40")}>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex flex-wrap items-center gap-2">
          <Badge variant={unknown ? "warning" : "outline"}>
            {CATEGORY_LABEL[cluster.category as ClusterCategory] ?? cluster.category}
          </Badge>
          {cluster.ruleFallback ? <Badge variant="warning">规则聚类</Badge> : null}
          <Badge variant="outline">{cluster.blocking}</Badge>
        </CardTitle>
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
            <div
              className={cn("h-full rounded-full", cluster.confidence >= 0.7 ? "bg-success" : "bg-warning")}
              style={{ width: `${Math.min(100, Math.max(0, cluster.confidence * 100))}%` }}
            />
          </div>
          <span className="font-mono text-xs text-muted-foreground">{cluster.confidence.toFixed(2)}</span>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm">{cluster.summary ?? "等待后端簇摘要"}</p>
        {cluster.evidenceHref ? (
          <a className="text-xs text-primary underline" href={cluster.evidenceHref}>
            证据链接
          </a>
        ) : (
          <p className="text-xs text-muted-foreground">证据链接需 API-130 返回</p>
        )}
        <div className="flex flex-wrap gap-2">
          <Input placeholder="人工修正类别" className="max-w-40" id={`cat-${cluster.id}`} />
          <Input placeholder="阻塞判断" className="max-w-40" id={`blk-${cluster.id}`} />
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              onCorrect?.({
                category: (document.getElementById(`cat-${cluster.id}`) as HTMLInputElement | null)?.value ?? "",
                blocking: (document.getElementById(`blk-${cluster.id}`) as HTMLInputElement | null)?.value ?? "",
              })
            }
          >
            提交修正留痕
          </Button>
          {applyVisible && bestFix ? (
            <Button
              size="sm"
              disabled={applyPending}
              onClick={() => onApply?.(bestFix)}
            >
              可应用（须审批）
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
