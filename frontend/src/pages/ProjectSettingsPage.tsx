import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ListEnvelope, MeProjection, ResourceEnvelope } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { StatusBadge } from "@/components/domain/StatusBadge";

export function ProjectSettingsPage() {
  const { projectId = "" } = useParams();

  const me = useQuery({
    queryKey: queryKeys.me,
    queryFn: () => api.get<ResourceEnvelope<MeProjection>>("API-005", "/api/v1/me"),
  });
  const members = useQuery({
    queryKey: queryKeys.members(projectId || "none"),
    queryFn: () =>
      api.get<ListEnvelope<Record<string, unknown>>>("API-013", `/api/v1/projects/${projectId}/members`),
    enabled: Boolean(projectId),
  });
  const quota = useQuery({
    queryKey: ["projects", projectId, "quota-view"],
    queryFn: () =>
      api.get<ResourceEnvelope<Record<string, unknown>>>("API-018", `/api/v1/projects/${projectId}/quota-view`),
    enabled: Boolean(projectId),
  });
  const notify = useQuery({
    queryKey: ["projects", projectId, "notification-subscriptions"],
    queryFn: () =>
      api.get<ResourceEnvelope<Record<string, unknown>>>(
        "API-019",
        `/api/v1/projects/${projectId}/notification-subscriptions`,
      ),
    enabled: Boolean(projectId),
  });

  const role =
    me.data?.data.projects.find((item) => item.project_id === projectId)?.role ??
    me.data?.data.projects[0]?.role;
  const viewer = role === "viewer";
  const memberItems = members.data?.data.items ?? [];
  const quotaView = asRecord(quota.data?.data.view);
  const channels = Array.isArray(notify.data?.data.channels) ? notify.data.data.channels : [];
  const categories = Array.isArray(notify.data?.data.categories) ? notify.data.data.categories : [];
  const pageError = members.error ?? quota.error ?? notify.error;

  return (
    <>
      <PageHeader
        title="项目设置"
        description="成员与角色（owner/admin/tester/viewer）· Jira 项目映射 · 项目级配额 · 通知订阅"
      />
      {!projectId ? (
        <Alert>
          <AlertDescription>请从项目进入设置页。</AlertDescription>
        </Alert>
      ) : (
        <>
          {viewer ? (
            <Alert>
              <AlertTitle>viewer 只读</AlertTitle>
              <AlertDescription>当前角色为 viewer，本页仅呈现，不提供发起或变更入口。</AlertDescription>
            </Alert>
          ) : null}
          <QueryGate isPending={members.isPending || quota.isPending || notify.isPending} error={pageError} apis={PAGE_APIS.P04}>
            <Tabs defaultValue="members">
              <TabsList>
                <TabsTrigger value="members">成员与角色</TabsTrigger>
                <TabsTrigger value="quota">配额</TabsTrigger>
                <TabsTrigger value="notify">通知订阅</TabsTrigger>
              </TabsList>
              <TabsContent value="members">
                {memberItems.length === 0 ? (
                  <EmptyState title="无成员" />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>姓名</TableHead>
                        <TableHead>邮箱</TableHead>
                        <TableHead>角色</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {memberItems.map((item, index) => (
                        <TableRow key={String(item.user_id ?? index)}>
                          <TableCell>{String(item.display_name ?? item.user_id ?? "")}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">{String(item.email ?? "—")}</TableCell>
                          <TableCell>
                            <StatusBadge status={String(item.role ?? "")} />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </TabsContent>
              <TabsContent value="quota">
                <Card>
                  <CardHeader>
                    <CardTitle>项目级配额视图</CardTitle>
                  </CardHeader>
                  <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                    <QuotaStat label="本项目 Token 消耗" value={quotaView.token_consumed_in_project} />
                    <QuotaStat label="执行并发 slot" value={quotaView.executor_slots_in_use_in_project} />
                    <QuotaStat label="压测并发" value={quotaView.perf_concurrency_in_use_in_project} />
                  </CardContent>
                </Card>
              </TabsContent>
              <TabsContent value="notify">
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <Card>
                    <CardHeader>
                      <CardTitle>渠道</CardTitle>
                    </CardHeader>
                    <CardContent className="flex flex-col gap-2">
                      {channels.length === 0 ? <p className="text-sm text-muted-foreground">无渠道投影</p> : null}
                      {channels.map((item, index) => {
                        const row = asRecord(item);
                        return (
                          <div key={String(row.channel_id ?? index)} className="flex items-center justify-between rounded-md border p-2">
                            <span className="text-sm">{String(row.channel_id ?? "")}</span>
                            <StatusBadge status={row.enabled === true ? "ACTIVE" : "DISABLED"} />
                          </div>
                        );
                      })}
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader>
                      <CardTitle>通知类别</CardTitle>
                    </CardHeader>
                    <CardContent className="flex flex-col gap-2">
                      {categories.length === 0 ? <p className="text-sm text-muted-foreground">无类别投影</p> : null}
                      {categories.map((item, index) => {
                        const row = asRecord(item);
                        return (
                          <div key={String(row.category ?? index)} className="flex items-center justify-between rounded-md border p-2">
                            <span className="text-sm">{String(row.category ?? "")}</span>
                            <StatusBadge status={row.enabled === true ? "ACTIVE" : "DISABLED"} />
                          </div>
                        );
                      })}
                    </CardContent>
                  </Card>
                </div>
              </TabsContent>
            </Tabs>
          </QueryGate>
        </>
      )}
    </>
  );
}

function QuotaStat({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-mono text-xl font-bold">{value == null ? "—" : String(value)}</p>
    </div>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}
