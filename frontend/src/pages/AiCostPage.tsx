import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ResourceEnvelope } from "@/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader, QueryGate } from "@/components/domain/PageState";

export function AiCostPage() {
  const windowStart = startOfUtcMonth();
  const windowEnd = new Date().toISOString();

  const query = useQuery({
    queryKey: queryKeys.cost,
    queryFn: () =>
      api.get<ResourceEnvelope<Record<string, unknown>>>("API-183", "/api/v1/ai/cost-dashboard", {
        from: windowStart,
        to: windowEnd,
        dimension: "workflow",
      }),
  });

  const data = query.data?.data ?? {};
  const totals = asRecord(data.totals);
  const costPerWorkflow = asRecord(totals.cost_per_workflow);
  const workflows = Object.entries(costPerWorkflow);

  return (
    <>
      <PageHeader title="AI 成本看板" description="部门 Token 消耗 · 采纳率 · 降级率 · 每工作流成本" />
      <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P21}>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Stat label="Token 消耗" value={formatUnknown(asRecord(totals.token_usage).total ?? totals.token_usage)} hint="部门聚合" />
          <Stat label="费用" value={formatUnknown(totals.cost)} hint="窗口内" />
          <Stat label="采纳率" value={formatUnknown(totals.adoption_rate)} hint="来自 AIInvocationLog" />
          <Stat label="降级率" value={formatUnknown(totals.degrade_rate)} hint="result=degraded" />
        </div>
        <Card>
          <CardHeader>
            <CardTitle>每工作流成本</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {workflows.length === 0 ? <p className="text-sm text-muted-foreground">无工作流拆分</p> : null}
            {workflows.map(([name, cost]) => (
              <div key={name} className="flex items-center justify-between rounded-md border p-2 text-sm">
                <span>{name}</span>
                <span className="font-mono">{formatUnknown(cost)}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </QueryGate>
    </>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="font-mono text-2xl font-bold">{value}</p>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}

function startOfUtcMonth(): string {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)).toISOString();
}

function formatUnknown(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}
