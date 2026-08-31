import { Badge } from "@/components/ui/badge";
import type { RiskLevel } from "@/api/types";
import { cn } from "@/lib/utils";

const TONE: Record<RiskLevel, string> = {
  L0: "border-risk-l0/30 text-risk-l0",
  L1: "border-risk-l1/30 text-risk-l1 bg-info-foreground",
  L2: "border-risk-l2/30 text-risk-l2 bg-warning-foreground",
  L3: "border-risk-l3/30 text-risk-l3 bg-warning-foreground",
  L4: "border-risk-l4/30 text-risk-l4 bg-destructive/10",
};

export function RiskBadge({ level }: { level: RiskLevel | string }) {
  const tone = TONE[level as RiskLevel] ?? "border-border text-muted-foreground";
  return (
    <Badge variant="outline" className={cn("font-mono", tone)}>
      {level}
    </Badge>
  );
}
