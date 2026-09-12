import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type {
  BlockingJudgment,
  ClusterCategory,
  CorrectionHistoryItem,
  FailureClusterFixPreview,
  SimilarFailureClusterItem,
} from "@/api/types";
import { cn } from "@/lib/utils";
import { MutateOnly } from "@/components/domain/PageState";

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
  summary?: string;
  ruleFallback?: boolean;
  canShowApply?: boolean;
  fixes?: FailureClusterFixPreview[];
  evidenceRefs?: string[];
  failureRefs?: string[];
  jiraIssue?: { key: string; external_request_id?: string };
  correctionHistory?: CorrectionHistoryItem[];
  similarItems?: SimilarFailureClusterItem[];
}

export function ClusterCard({
  cluster,
  onCorrect,
  onApply,
  onCreateJira,
  applyPending,
  correctPending,
  jiraPending,
  showJiraButton,
}: {
  cluster: ClusterCardModel;
  onCorrect?: (next: { category: string; blocking: string }) => void;
  onApply?: (fix: FailureClusterFixPreview) => void;
  onCreateJira?: () => void;
  applyPending?: boolean;
  correctPending?: boolean;
  jiraPending?: boolean;
  showJiraButton?: boolean;
}) {
  const [categoryDraft, setCategoryDraft] = useState("");
  const [blockingDraft, setBlockingDraft] = useState("");
  const unknown = cluster.category === "unknown";
  const bestFix = (cluster.fixes ?? []).find((fix) => fix.confidence >= 0.7);
  const applyVisible = Boolean(
    cluster.canShowApply &&
      !cluster.ruleFallback &&
      cluster.confidence >= 0.7 &&
      bestFix,
  );
  const history = cluster.correctionHistory ?? [];
  const similar = cluster.similarItems ?? [];

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
        {(cluster.failureRefs ?? []).length > 0 ? (
          <div className="flex flex-col gap-1">
            <p className="text-xs font-medium text-muted-foreground">失败用例</p>
            {(cluster.failureRefs ?? []).map((ref) => (
              <Link
                key={ref}
                className="font-mono text-xs text-primary underline"
                to={`/test-center/case-results/${ref}`}
              >
                {ref}
              </Link>
            ))}
          </div>
        ) : null}
        {(cluster.evidenceRefs ?? []).length > 0 ? (
          <div className="flex flex-col gap-1">
            <p className="text-xs font-medium text-muted-foreground">证据引用</p>
            {(cluster.evidenceRefs ?? []).map((ref) => (
              <span key={ref} className="font-mono text-xs text-foreground">
                {ref}
              </span>
            ))}
          </div>
        ) : null}
        {cluster.jiraIssue ? (
          <p className="text-xs text-muted-foreground">
            Jira 缺陷：<span className="font-mono text-foreground">{cluster.jiraIssue.key}</span>
          </p>
        ) : null}
        <MutateOnly>
          <div className="flex flex-wrap gap-2">
            <Input
              placeholder="人工修正类别"
              className="max-w-40"
              value={categoryDraft}
              onChange={(event) => setCategoryDraft(event.target.value)}
            />
            <Input
              placeholder="阻塞判断"
              className="max-w-40"
              value={blockingDraft}
              onChange={(event) => setBlockingDraft(event.target.value)}
            />
            <Button
              size="sm"
              variant="outline"
              disabled={correctPending}
              onClick={() => onCorrect?.({ category: categoryDraft, blocking: blockingDraft })}
            >
              提交修正留痕
            </Button>
            {applyVisible && bestFix ? (
              <Button size="sm" disabled={applyPending} onClick={() => onApply?.(bestFix)}>
                可应用（须审批）
              </Button>
            ) : null}
            {showJiraButton ? (
              <Button size="sm" variant="secondary" disabled={jiraPending} onClick={() => onCreateJira?.()}>
                一键创建 Jira 缺陷
              </Button>
            ) : null}
          </div>
        </MutateOnly>
        <div className="rounded-md border border-dashed bg-muted/30 p-2 text-xs">
          <p className="mb-1 font-medium text-foreground">修正历史</p>
          {history.length === 0 ? (
            <p className="text-muted-foreground">暂无人工修正记录</p>
          ) : (
            history.map((entry, index) => (
              <p key={`${entry.timestamp}-${index}`} className="font-mono text-muted-foreground">
                {entry.field}: {String(entry.old)} → {String(entry.new)}
              </p>
            ))
          )}
        </div>
        <div className="rounded-md border border-dashed bg-muted/30 p-2 text-xs">
          <p className="mb-1 font-medium text-foreground">相似失败</p>
          {similar.length === 0 ? (
            <p className="text-muted-foreground">无相似失败</p>
          ) : (
            similar.map((item) => (
              <Link
                key={item.id}
                className="mb-1 block font-mono text-primary underline"
                to={`/test-center/runs/${item.test_run_id}`}
              >
                {item.id} · score {item.similarity_score?.toFixed(1) ?? "—"}
              </Link>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}
