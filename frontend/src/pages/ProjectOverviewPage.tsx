import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ListEnvelope, ProjectListItem, ProjectOverview, ResourceEnvelope } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { StatusBadge } from "@/components/domain/StatusBadge";

const LIST_APIS = PAGE_APIS.session.filter((item) => item.id === "API-011");

export function ProjectOverviewPage() {
  const { projectId } = useParams();
  if (!projectId) {
    return <ProjectListView />;
  }
  return <ProjectDetailView projectId={projectId} />;
}

function ProjectListView() {
  const query = useQuery({
    queryKey: queryKeys.projects,
    queryFn: () => api.get<ListEnvelope<ProjectListItem>>("API-011", "/api/v1/projects"),
  });
  const items = query.data?.data.items ?? [];

  return (
    <>
      <PageHeader title="项目总览" description="工具连接状态 · Jira 映射 · 最近活动。无手工建项目（Jira 只读镜像）。" />
      <QueryGate isPending={query.isPending} error={query.error} apis={LIST_APIS}>
        {items.length === 0 ? (
          <EmptyState title="无项目" hint="空集表示当前用户无项目成员身份，不是错误。" />
        ) : (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
            {items.map((item) => (
              <Link key={item.id} to={`/projects/${item.id}/overview`}>
                <Card className="h-full hover:border-primary/40" data-testid="project-list-item">
                  <CardHeader>
                    <CardTitle>{item.name}</CardTitle>
                    <p className="font-mono text-xs text-muted-foreground">
                      Jira: {item.jira_project_key ?? "未映射"}
                    </p>
                  </CardHeader>
                  <CardContent>
                    <StatusBadge status={item.my_role} />
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </QueryGate>
    </>
  );
}

function ProjectDetailView({ projectId }: { projectId: string }) {
  const query = useQuery({
    queryKey: queryKeys.project(projectId),
    queryFn: () =>
      api.get<ResourceEnvelope<ProjectOverview>>("API-012", `/api/v1/projects/${projectId}`),
  });
  const data = query.data?.data;
  const connectors = data?.connector_health ?? [];
  const activity = data?.recent_activity ?? [];

  return (
    <>
      <PageHeader title={data?.name ?? "项目总览"} description="工具连接状态 · Jira 映射 · 最近活动" />
      <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P02}>
        {data ? (
          <>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <Card>
                <CardHeader>
                  <CardTitle>工具连接状态</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-2">
                  {connectors.length === 0 ? <p className="text-sm text-muted-foreground">无连接摘要</p> : null}
                  {connectors.map((row) => {
                    const healthy = row.healthy === true;
                    return (
                      <div key={row.connector_id} className="flex items-center justify-between rounded-md border p-2">
                        <div className="flex items-center gap-2">
                          <span className={healthy ? "size-2 rounded-full bg-success" : "size-2 rounded-full bg-destructive"} />
                          <span className="text-sm">{row.name ?? row.type}</span>
                          <Badge variant="outline">{row.type}</Badge>
                        </div>
                        <StatusBadge status={healthy ? "ACTIVE" : "DEGRADED"} />
                      </div>
                    );
                  })}
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Jira 映射</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-1">
                  <p className="font-mono text-sm">{data.jira.project_key ?? "未映射"}</p>
                  <p className="text-xs text-muted-foreground">只读同步，平台不写回 Jira 项目元数据。</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>角色</CardTitle>
                </CardHeader>
                <CardContent>
                  <StatusBadge status={data.my_role} />
                </CardContent>
              </Card>
            </div>
            <Card>
              <CardHeader>
                <CardTitle>最近活动</CardTitle>
              </CardHeader>
              <CardContent>
                {activity.length === 0 ? (
                  <EmptyState title="无最近活动" />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>时间</TableHead>
                        <TableHead>摘要</TableHead>
                        <TableHead>对象</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {activity.map((row, index) => (
                        <TableRow key={row.audit_event_id ?? `${row.occurred_at}-${index}`}>
                          <TableCell className="text-xs text-muted-foreground">{row.occurred_at}</TableCell>
                          <TableCell>{row.summary}</TableCell>
                          <TableCell className="font-mono text-xs">{row.resource_type ?? ""}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </>
        ) : null}
      </QueryGate>
    </>
  );
}
