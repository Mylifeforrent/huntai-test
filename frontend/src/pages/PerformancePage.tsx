import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import type { ListEnvelope } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { UndevelopedCallout } from "@/components/domain/UndevelopedCallout";
import { useUrlState } from "@/hooks/useUrlState";

export function PerformancePage() {
  const { get, set } = useUrlState();
  const projectId = get("projectId");
  const [killOpen, setKillOpen] = useState(false);
  const [killTried, setKillTried] = useState(false);

  const query = useQuery({
    queryKey: ["perf-baselines", projectId],
    queryFn: () =>
      api.get<ListEnvelope<Record<string, unknown>>>("API-056", "/api/v1/perf-baselines", {
        project_id: projectId,
      }),
    enabled: Boolean(projectId),
  });
  const items = query.data?.data.items ?? [];

  function tighten() {
    setKillTried(true);
    void api
      .post("API-199", "/api/v1/organizations/current/capability-controls/tighten", {
        expected_version: 1,
        target: { level: "module", module: "perf" },
        reason: "performance kill switch",
      })
      .catch(() => undefined);
  }

  return (
    <>
      <PageHeader
        title="性能压测"
        description="场景配置（白名单环境+护栏提示）· 基线对比 · kill switch · 压力机自监控。M3。"
      />
      <Alert>
        <AlertTitle>无自动重试</AlertTitle>
        <AlertDescription>
          压测任务失败或 kill switch 关停导致 STOPPING 后，严禁自动重试。护栏仅允许白名单环境。
        </AlertDescription>
      </Alert>
      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="projectId（API-056 必填）"
          value={projectId}
          onChange={(event) => set({ projectId: event.target.value })}
          className="max-w-72"
        />
        <Button variant="destructive" onClick={() => setKillOpen(true)}>
          Kill switch 关停压测模块
        </Button>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>白名单环境与护栏</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm text-muted-foreground">
          <p>仅白名单执行环境可发起压测。高风险场景走 perf_high_risk 审批（L2+）。</p>
          <p>压力机自监控指标由服务端下发，前端不推演容量。</p>
        </CardContent>
      </Card>
      {!projectId ? (
        <Alert>
          <AlertDescription>填写 projectId 后查询性能基线（API-056）。</AlertDescription>
        </Alert>
      ) : (
        <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P16}>
          {items.length === 0 ? (
            <EmptyState title="无性能基线" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>基线</TableHead>
                  <TableHead>场景用例</TableHead>
                  <TableHead>活跃</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item, index) => (
                  <TableRow key={String(item.id ?? index)}>
                    <TableCell className="font-mono text-xs">{String(item.id ?? "")}</TableCell>
                    <TableCell className="font-mono text-xs">{String(item.scenario_test_case_id ?? "")}</TableCell>
                    <TableCell>
                      <StatusBadge status={item.is_active === true ? "ACTIVE" : "DISABLED"} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </QueryGate>
      )}
      {killTried ? <UndevelopedCallout apis={PAGE_APIS.P16} action="压测 kill switch API-199" /> : null}
      <AlertDialog open={killOpen} onOpenChange={setKillOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>立即关停压测模块？</AlertDialogTitle>
            <AlertDialogDescription>
              关停走 API-199（L1 即时）。在途压测可能进入 STOPPING。关停后不得自动重试。恢复须走 kill_switch_restore，不能用 tighten 放开。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={tighten}>立即关停</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
