import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ResourceEnvelope } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { PageHeader, QueryGate } from "@/components/domain/PageState";
import { AiDegradeBanner } from "@/components/domain/AiDegradeBanner";
import { UndevelopedCallout } from "@/components/domain/UndevelopedCallout";

const ABILITIES = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"] as const;
const MODULES = ["copilot", "release", "perf"] as const;
const CONNECTOR_WRITES = ["jira", "github"] as const;

const LEVELS = [
  { id: "ability", title: "单能力", hint: "A1–A8 独立能力开关" },
  { id: "module", title: "模块", hint: "Copilot / Release / 压测" },
  { id: "connector", title: "连接器写入", hint: "外部写入通道" },
  { id: "global", title: "全局 AI", hint: "最高级别停机" },
] as const;

type PendingAction = { kind: "tighten" | "restore"; level: string; id: string; label: string };

export function AiSwitchPage() {
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [tried, setTried] = useState("");

  const query = useQuery({
    queryKey: queryKeys.organization,
    queryFn: () => api.get<ResourceEnvelope<Record<string, unknown>>>("API-010", "/api/v1/organizations/current"),
  });

  const org = query.data?.data ?? {};
  const controls = asRecord(org.capability_controls);
  const globalOff = controls.ai_global_tightened === true;
  const tightCaps = toStringList(controls.tightened_capabilities);
  const tightMods = toStringList(controls.tightened_modules);
  const banner = typeof controls.banner_scope === "string" ? controls.banner_scope : undefined;
  const orgId = String(org.id ?? "");
  const orgVersion = org.version;

  function confirmPending() {
    if (!pending) return;
    if (pending.kind === "tighten") {
      setTried("tighten");
      const target: Record<string, unknown> = { level: pending.level };
      if (pending.level === "ability") target.capability_id = pending.id;
      if (pending.level === "module") target.module = pending.id;
      if (pending.level === "connector") target.connector_id = pending.id;
      void api
        .post("API-199", "/api/v1/organizations/current/capability-controls/tighten", {
          expected_version: orgVersion,
          target,
          reason: `tighten ${pending.label}`,
        })
        .catch(() => undefined);
    } else {
      setTried("restore");
      void api
        .post("API-120", "/api/v1/action-previews", {
          action_type: "kill_switch_restore",
          target_object_type: "organization",
          target_object_id: orgId,
          payload: { target: { level: pending.level, id: pending.id } },
          expected_target_version: orgVersion,
        })
        .catch(() => undefined);
    }
    setPending(null);
  }

  return (
    <>
      <PageHeader title="AI 能力开关与降级" description="四级 kill switch · 当前降级状态与横幅生效范围 · 压测 kill switch 演练入口" />
      <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P23}>
        <AiDegradeBanner active={globalOff || tightCaps.length > 0 || tightMods.length > 0} scope={banner} />
        <Alert variant="warning">
          <AlertTitle>开关方向不对称</AlertTitle>
          <AlertDescription>
            关停（收紧）= L1，走 API-199，即时生效不走审批。恢复（放开）= L3，走 API-120 action_type=kill_switch_restore。禁止用 tighten 放开。
          </AlertDescription>
        </Alert>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-xs">
            <p className="font-semibold text-destructive">关停（收紧）= L1</p>
            <p className="text-muted-foreground">即时生效，不走审批。事故响应不得被审批阻塞。</p>
          </div>
          <div className="rounded-md border border-primary/20 bg-accent p-3 text-xs">
            <p className="font-semibold">恢复（放开）= L3</p>
            <p className="text-muted-foreground">须 kill_switch_restore 审批，防止误操作恢复。</p>
          </div>
        </div>
        {LEVELS.map((level) => (
          <Card key={level.id}>
            <CardHeader>
              <CardTitle>
                {level.title}
                <span className="ml-2 text-xs font-normal text-muted-foreground">{level.hint}</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {rowsFor(level.id).map((row) => {
                const off =
                  level.id === "global"
                    ? globalOff
                    : level.id === "ability"
                      ? tightCaps.includes(row.id) || globalOff
                      : tightMods.includes(row.id) || globalOff;
                return (
                  <div key={row.id} className="flex items-center justify-between rounded-md border p-3">
                    <div className="flex items-center gap-2">
                      <span className={off ? "size-2 rounded-full bg-muted-foreground" : "size-2 rounded-full bg-success"} />
                      <span className="text-sm">{row.label}</span>
                      <Badge variant="outline">{off ? "已关停" : "运行中"}</Badge>
                    </div>
                    {off ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setPending({ kind: "restore", level: level.id, id: row.id, label: row.label })}
                      >
                        申请恢复 (L3)
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => setPending({ kind: "tighten", level: level.id, id: row.id, label: row.label })}
                      >
                        关停 (L1)
                      </Button>
                    )}
                  </div>
                );
              })}
            </CardContent>
          </Card>
        ))}
      </QueryGate>
      {tried === "tighten" ? <UndevelopedCallout apis={PAGE_APIS.P23} action="关停 API-199" /> : null}
      {tried === "restore" ? <UndevelopedCallout apis={PAGE_APIS.P23} action="恢复须走 kill_switch_restore（API-120），不得调用 tighten" /> : null}
      <AlertDialog open={Boolean(pending)} onOpenChange={(open) => !open && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pending?.kind === "tighten" ? `立即关停：${pending.label}` : `申请恢复：${pending?.label ?? ""}`}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pending?.kind === "tighten"
                ? "关停动作 L1，即时生效，不走审批。写入 AuditEvent。不得用本接口恢复。"
                : "恢复为 L3，须 API-120 action_type=kill_switch_restore。禁止 POST tighten 放开。"}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={confirmPending}>
              {pending?.kind === "tighten" ? "立即关停" : "发起恢复审批"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

function rowsFor(level: string): Array<{ id: string; label: string }> {
  if (level === "ability") return ABILITIES.map((id) => ({ id, label: id }));
  if (level === "module") {
    return MODULES.map((id) => ({
      id,
      label: id === "copilot" ? "Copilot 模块" : id === "release" ? "Release AI 模块" : "压测 AI 模块",
    }));
  }
  if (level === "connector") return CONNECTOR_WRITES.map((id) => ({ id, label: `${id} 连接器写入` }));
  return [{ id: "global", label: "全局 AI" }];
}

function toStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}
