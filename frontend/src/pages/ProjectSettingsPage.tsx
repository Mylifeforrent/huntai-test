import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type {
  ListEnvelope,
  MeProjection,
  ProjectMember,
  ProjectMemberItem,
  ProjectQuotaView,
  ProjectRole,
  ResourceEnvelope,
} from "@/api/types";
import { PROJECT_ROLES } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  CommandFeedback,
  PageHeader,
  QueryGate,
  EmptyState,
} from "@/components/domain/PageState";
import { UndevelopedCallout } from "@/components/domain/UndevelopedCallout";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { tokenRemainingProjection } from "@/lib/utils";
import { useViewport } from "@/hooks/useViewport";

export function ProjectSettingsPage() {
  const { projectId = "" } = useParams();
  const { canMutate } = useViewport();
  const queryClient = useQueryClient();
  const [commandError, setCommandError] = useState<unknown>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [addUserId, setAddUserId] = useState("");
  const [addRole, setAddRole] = useState<ProjectRole>("viewer");

  const me = useQuery({
    queryKey: queryKeys.me,
    queryFn: () => api.get<ResourceEnvelope<MeProjection>>("API-005", "/api/v1/me"),
  });
  const members = useQuery({
    queryKey: queryKeys.members(projectId || "none"),
    queryFn: () =>
      api.get<ListEnvelope<ProjectMemberItem>>("API-013", `/api/v1/projects/${projectId}/members`),
    enabled: Boolean(projectId),
  });
  const quotaView = useQuery({
    queryKey: ["projects", projectId, "quota-view"],
    queryFn: () =>
      api.get<ResourceEnvelope<ProjectQuotaView>>("API-018", `/api/v1/projects/${projectId}/quota-view`),
    enabled: Boolean(projectId),
  });

  const myRole =
    me.data?.data.memberships.find((item) => item.project_id === projectId)?.role ?? null;
  const viewer = myRole === "viewer";
  const canWrite = canMutate && (myRole === "owner" || myRole === "admin");
  const memberItems = members.data?.data.items ?? [];

  const invalidateMembers = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.members(projectId) });
  };

  const addMember = useMutation({
    mutationFn: () =>
      api.post<ResourceEnvelope<ProjectMember>>(
        "API-014",
        `/api/v1/projects/${projectId}/members`,
        { user_id: addUserId.trim(), role: addRole },
      ),
    onMutate: () => {
      setCommandError(null);
      setPendingAction("添加成员");
    },
    onSuccess: () => {
      setAddUserId("");
      setPendingAction(null);
      invalidateMembers();
    },
    onError: (error) => {
      setPendingAction(null);
      setCommandError(error);
    },
  });

  const patchRole = useMutation({
    mutationFn: (input: { userId: string; role: ProjectRole }) =>
      api.patch<ResourceEnvelope<ProjectMember>>(
        "API-015",
        `/api/v1/projects/${projectId}/members/${input.userId}`,
        { role: input.role },
      ),
    onMutate: () => {
      setCommandError(null);
      setPendingAction("变更角色");
    },
    onSuccess: () => {
      setPendingAction(null);
      invalidateMembers();
    },
    onError: (error) => {
      setPendingAction(null);
      setCommandError(error);
    },
  });

  const removeMember = useMutation({
    mutationFn: (userId: string) =>
      api.delete("API-016", `/api/v1/projects/${projectId}/members/${userId}`),
    onMutate: () => {
      setCommandError(null);
      setPendingAction("移除成员");
    },
    onSuccess: () => {
      setPendingAction(null);
      invalidateMembers();
    },
    onError: (error) => {
      setPendingAction(null);
      setCommandError(error);
    },
  });

  const writeBusy = addMember.isPending || patchRole.isPending || removeMember.isPending;

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
          <Tabs defaultValue="members">
            <TabsList>
              <TabsTrigger value="members">成员与角色</TabsTrigger>
              <TabsTrigger value="quota">配额</TabsTrigger>
              <TabsTrigger value="notify">通知订阅</TabsTrigger>
            </TabsList>
            <TabsContent value="members">
              <QueryGate
                isPending={members.isPending || me.isPending}
                error={members.error ?? me.error}
                apis={PAGE_APIS.P04_members}
              >
                {pendingAction ? (
                  <p className="mb-3 text-sm text-muted-foreground" data-testid="members-pending">
                    {pendingAction}受理中…
                  </p>
                ) : null}
                <CommandFeedback error={commandError} apis={PAGE_APIS.P04_members} action="成员变更" />
                {canWrite ? (
                  <form
                    className="mb-4 flex flex-wrap items-end gap-3 rounded-md border p-3"
                    data-testid="add-member-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (!addUserId.trim()) return;
                      addMember.mutate();
                    }}
                  >
                    <div className="flex min-w-56 flex-1 flex-col gap-1">
                      <Label htmlFor="add-user-id">用户 ID</Label>
                      <Input
                        id="add-user-id"
                        value={addUserId}
                        onChange={(event) => setAddUserId(event.target.value)}
                        placeholder="user UUID"
                        disabled={writeBusy}
                      />
                    </div>
                    <div className="flex w-40 flex-col gap-1">
                      <Label>角色</Label>
                      <Select
                        value={addRole}
                        onValueChange={(value) => setAddRole(value as ProjectRole)}
                        disabled={writeBusy}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {PROJECT_ROLES.map((role) => (
                            <SelectItem key={role} value={role}>
                              {role}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <Button type="submit" disabled={writeBusy || !addUserId.trim()}>
                      添加成员
                    </Button>
                  </form>
                ) : null}
                {memberItems.length === 0 ? (
                  <EmptyState title="无成员" />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>姓名</TableHead>
                        <TableHead>邮箱</TableHead>
                        <TableHead>角色</TableHead>
                        {canWrite ? <TableHead>操作</TableHead> : null}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {memberItems.map((item) => (
                        <TableRow key={item.user_id} data-testid="member-row">
                          <TableCell>{item.display_name ?? item.user_id}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {"email" in item && item.email ? item.email : "—"}
                          </TableCell>
                          <TableCell>
                            {canWrite ? (
                              <Select
                                value={item.role}
                                onValueChange={(value) =>
                                  patchRole.mutate({ userId: item.user_id, role: value as ProjectRole })
                                }
                                disabled={writeBusy}
                              >
                                <SelectTrigger className="w-32" data-testid="member-role-select">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  {PROJECT_ROLES.map((role) => (
                                    <SelectItem key={role} value={role}>
                                      {role}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            ) : (
                              <StatusBadge status={item.role} />
                            )}
                          </TableCell>
                          {canWrite ? (
                            <TableCell>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                disabled={writeBusy}
                                data-testid="remove-member"
                                onClick={() => removeMember.mutate(item.user_id)}
                              >
                                移除
                              </Button>
                            </TableCell>
                          ) : null}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </QueryGate>
            </TabsContent>
            <TabsContent value="quota">
              <QueryGate isPending={quotaView.isPending} error={quotaView.error} apis={PAGE_APIS.P04_quota}>
                <p className="text-sm text-muted-foreground">组织 Token 余量（服务端投影，禁止本地相减）</p>
                <p className="font-mono text-2xl font-bold tabular-nums">
                  {tokenRemainingProjection(quotaView.data?.data.view.org_remaining) ?? "—"}
                </p>
              </QueryGate>
            </TabsContent>
            <TabsContent value="notify">
              <UndevelopedCallout apis={PAGE_APIS.P04_notify} action="通知订阅" />
            </TabsContent>
          </Tabs>
        </>
      )}
    </>
  );
}
