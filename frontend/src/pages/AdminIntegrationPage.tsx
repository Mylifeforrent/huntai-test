import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type {
  ApiTokenIssued,
  ApiTokenListItem,
  ApiTokenScope,
  ConnectorListItem,
  ConnectorType,
  ListEnvelope,
  OutboundChannelPutItem,
  OutboundChannelsListEnvelope,
  ResourceEnvelope,
  WebhookDeliveryItem,
} from "@/api/types";
import { API_TOKEN_SCOPES } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { MutateOnly, PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { UndevelopedCallout } from "@/components/domain/UndevelopedCallout";
import { useSession } from "@/hooks/useSession";

export function AdminIntegrationPage() {
  const queryClient = useQueryClient();
  const session = useSession();
  const memberships = session.me?.memberships ?? [];
  const projectIds = memberships.map((m) => m.project_id);
  const canIssue = projectIds.length > 0;
  const canWriteConnector = memberships.some(
    (membership) => membership.role === "owner" || membership.role === "admin",
  );

  const [registerType, setRegisterType] = useState<ConnectorType>("jira");
  const [registerName, setRegisterName] = useState("");
  const [registerAuthMethod, setRegisterAuthMethod] = useState("");
  const [registerActionContract, setRegisterActionContract] = useState("{}");
  const [registerHasCredential, setRegisterHasCredential] = useState(false);
  const [registerError, setRegisterError] = useState<unknown>(null);
  const [registerSuccess, setRegisterSuccess] = useState(false);

  const [updateConnectorId, setUpdateConnectorId] = useState("");
  const [updateName, setUpdateName] = useState("");
  const [updateActionContract, setUpdateActionContract] = useState("{}");
  const [updateDisableOutbound, setUpdateDisableOutbound] = useState(false);
  const [updateError, setUpdateError] = useState<unknown>(null);
  const [updateSuccess, setUpdateSuccess] = useState(false);

  const [issuedToken, setIssuedToken] = useState<string | null>(null);
  const [tokenName, setTokenName] = useState("");
  const [selectedScopes, setSelectedScopes] = useState<ApiTokenScope[]>(["read"]);
  const [expiresAtLocal, setExpiresAtLocal] = useState("");
  const [issueError, setIssueError] = useState<unknown>(null);
  const [revokeError, setRevokeError] = useState<unknown>(null);
  const [selectedConnector, setSelectedConnector] = useState("");
  const [outboundConnectorId, setOutboundConnectorId] = useState("");
  const [outboundDraft, setOutboundDraft] = useState<OutboundChannelPutItem[]>([]);
  const [outboundClearArmed, setOutboundClearArmed] = useState(false);
  const [outboundSaveError, setOutboundSaveError] = useState<unknown>(null);

  const connectors = useQuery({
    queryKey: queryKeys.connectors({ scope: "org" }),
    queryFn: () => api.get<ListEnvelope<ConnectorListItem>>("API-160", "/api/v1/connectors"),
  });
  const tokens = useQuery({
    queryKey: queryKeys.apiTokens,
    queryFn: () => api.get<ListEnvelope<ApiTokenListItem>>("API-170", "/api/v1/api-tokens"),
  });
  const connectorId = selectedConnector || String(connectors.data?.data.items[0]?.id ?? "");
  const outboundId = outboundConnectorId || String(connectors.data?.data.items[0]?.id ?? "");
  const outboundChannels = useQuery({
    queryKey: ["connectors", outboundId, "outbound-channels"],
    queryFn: () =>
      api.get<OutboundChannelsListEnvelope>(
        "API-165",
        `/api/v1/connectors/${outboundId}/outbound-channels`,
      ),
    enabled: Boolean(outboundId),
  });
  const deliveries = useQuery({
    queryKey: ["connectors", connectorId, "webhook-deliveries"],
    queryFn: () =>
      api.get<ListEnvelope<WebhookDeliveryItem>>(
        "API-164",
        `/api/v1/connectors/${connectorId}/webhook-deliveries`,
      ),
    enabled: Boolean(connectorId),
  });

  const connectorItems = connectors.data?.data.items ?? [];
  const updateTargetId = updateConnectorId || String(connectorItems[0]?.id ?? "");
  const updateTarget = connectorItems.find((item) => String(item.id) === updateTargetId);

  useEffect(() => {
    if (!updateTarget) {
      return;
    }
    setUpdateName(String(updateTarget.name ?? ""));
    setUpdateActionContract(JSON.stringify(updateTarget.action_contract ?? {}, null, 2));
    setUpdateDisableOutbound(false);
  }, [updateTargetId, updateTarget?.version, updateTarget?.name]);
  const tokenItems = tokens.data?.data.items ?? [];
  const deliveryItems = deliveries.data?.data.items ?? [];
  const outboundItems = outboundChannels.data?.data.items ?? [];
  const outboundVersion = outboundChannels.data?.data.connector_version ?? 1;
  const pageError = connectors.error ?? tokens.error;
  const canSaveOutboundDraft =
    Boolean(outboundId) &&
    outboundDraft.length > 0 &&
    outboundDraft.every((item) => {
      const kind = item.kind.trim();
      const ref = item.endpoint_ref?.trim() ?? "";
      return kind.length > 0 && /^env:[A-Z][A-Z0-9_]*$/.test(ref);
    });

  function putOutboundChannels(channels: OutboundChannelPutItem[]) {
    if (!outboundId) return;
    setOutboundSaveError(null);
    void api
      .put<OutboundChannelsListEnvelope>(
        "API-166",
        `/api/v1/connectors/${outboundId}/outbound-channels`,
        {
          expected_version: outboundVersion,
          channels,
        },
      )
      .then(() => {
        setOutboundDraft([]);
        setOutboundClearArmed(false);
        void queryClient.invalidateQueries({ queryKey: ["connectors", outboundId, "outbound-channels"] });
      })
      .catch((error: unknown) => {
        setOutboundSaveError(error);
      });
  }

  function saveOutboundChannels() {
    if (!canSaveOutboundDraft) return;
    putOutboundChannels(
      outboundDraft.map((item) => ({
        kind: item.kind.trim(),
        is_primary: item.is_primary,
        endpoint_ref: item.endpoint_ref?.trim() ?? "",
      })),
    );
  }

  function clearOutboundChannels() {
    if (!outboundId) return;
    if (!outboundClearArmed) {
      setOutboundClearArmed(true);
      return;
    }
    putOutboundChannels([]);
  }

  function toggleScope(scope: ApiTokenScope) {
    setSelectedScopes((prev) => {
      if (prev.includes(scope)) {
        const next = prev.filter((item) => item !== scope);
        return next.length > 0 ? next : prev;
      }
      return [...prev, scope];
    });
  }

  function issueToken() {
    if (!canIssue || selectedScopes.length === 0 || !expiresAtLocal) {
      return;
    }
    setIssueError(null);
    setIssuedToken(null);
    const expiresAt = new Date(expiresAtLocal);
    if (Number.isNaN(expiresAt.getTime())) {
      return;
    }
    void api
      .post<ResourceEnvelope<ApiTokenIssued>>("API-171", "/api/v1/api-tokens", {
        name: tokenName || undefined,
        scopes: selectedScopes,
        project_ids: projectIds,
        expires_at: expiresAt.toISOString(),
      })
      .then((body) => {
        const token = body.data?.token;
        if (token) setIssuedToken(token);
        void queryClient.invalidateQueries({ queryKey: queryKeys.apiTokens });
      })
      .catch((error: unknown) => {
        setIssueError(error);
      });
  }

  function parseActionContract(raw: string): Record<string, unknown> | null {
    try {
      const parsed = JSON.parse(raw) as unknown;
      if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      return null;
    }
    return null;
  }

  function registerConnector() {
    const actionContract = parseActionContract(registerActionContract);
    if (!registerName.trim() || !registerAuthMethod.trim() || actionContract === null) {
      return;
    }
    setRegisterError(null);
    setRegisterSuccess(false);
    void api
      .post<ResourceEnvelope<ConnectorListItem>>("API-162", "/api/v1/connectors", {
        type: registerType,
        name: registerName.trim(),
        auth_method: registerAuthMethod.trim(),
        action_contract: actionContract,
        ...(registerHasCredential ? { has_credential_binding: true } : {}),
      })
      .then(() => {
        setRegisterSuccess(true);
        setRegisterName("");
        setRegisterAuthMethod("");
        setRegisterActionContract("{}");
        setRegisterHasCredential(false);
        void queryClient.invalidateQueries({ queryKey: queryKeys.connectors({ scope: "org" }) });
      })
      .catch((error: unknown) => {
        setRegisterError(error);
      });
  }

  function updateConnector() {
    if (!updateTarget) return;
    const actionContract = parseActionContract(updateActionContract);
    if (!updateName.trim() || actionContract === null) {
      return;
    }
    const body: {
      expected_version: number;
      name: string;
      action_contract: Record<string, unknown>;
      outbound_write_enabled?: boolean;
    } = {
      expected_version: updateTarget.version,
      name: updateName.trim(),
      action_contract: actionContract,
    };
    if (updateTarget.outbound_write_enabled === true && updateDisableOutbound) {
      body.outbound_write_enabled = false;
    }
    setUpdateError(null);
    setUpdateSuccess(false);
    void api
      .patch<ResourceEnvelope<ConnectorListItem>>(
        "API-163",
        `/api/v1/connectors/${updateTargetId}`,
        body,
      )
      .then(() => {
        setUpdateSuccess(true);
        setUpdateDisableOutbound(false);
        void queryClient.invalidateQueries({ queryKey: queryKeys.connectors({ scope: "org" }) });
      })
      .catch((error: unknown) => {
        setUpdateError(error);
      });
  }

  function revoke(id: string) {
    setRevokeError(null);
    void api
      .post("API-172", `/api/v1/api-tokens/${id}/revocations`, {})
      .then(() => {
        void queryClient.invalidateQueries({ queryKey: queryKeys.apiTokens });
      })
      .catch((error: unknown) => {
        setRevokeError(error);
      });
  }

  return (
    <>
      <PageHeader
        title="集成中心"
        description="组织级连接器 · 入站 webhook 投递 · 出站通知渠道 · ApiToken 签发与吊销"
      />
      <Alert>
        <AlertTitle>Token 明文纪律</AlertTitle>
        <AlertDescription>列表与再 GET 只返回 token_prefix。明文仅 API-171 签发响应出现一次；本页不缓存、不回显伪造 token。</AlertDescription>
      </Alert>
      <QueryGate isPending={connectors.isPending || tokens.isPending} error={pageError} apis={PAGE_APIS.P25}>
        <Tabs defaultValue="connectors">
          <TabsList>
            <TabsTrigger value="connectors">连接器</TabsTrigger>
            <TabsTrigger value="webhooks">Webhook 投递</TabsTrigger>
            <TabsTrigger value="outbound" data-testid="integration-tab-outbound">出站渠道</TabsTrigger>
            <TabsTrigger value="tokens" data-testid="integration-tab-tokens">ApiToken</TabsTrigger>
          </TabsList>
          <TabsContent value="connectors">
            {canWriteConnector ? (
              <Card className="mb-4">
                <CardHeader>
                  <CardTitle>注册连接器（API-162）</CardTitle>
                </CardHeader>
                <CardContent className="flex max-w-lg flex-col gap-3">
                  <Alert>
                    <AlertDescription>
                      未声明副作用的 action_contract 默认拒绝。列表出现 ≠ 健康绿 ≠ 出站已通 ≠ 已触发 TestRun。
                    </AlertDescription>
                  </Alert>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="register-type">类型</Label>
                    <select
                      id="register-type"
                      data-testid="register-type"
                      className="rounded-md border px-3 py-2 text-sm"
                      value={registerType}
                      onChange={(e) => setRegisterType(e.target.value as ConnectorType)}
                    >
                      <option value="jira">jira</option>
                      <option value="github">github</option>
                      <option value="ci">ci</option>
                      <option value="release">release</option>
                    </select>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="register-name">名称</Label>
                    <Input
                      id="register-name"
                      data-testid="register-name"
                      value={registerName}
                      onChange={(e) => setRegisterName(e.target.value)}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="register-auth-method">auth_method</Label>
                    <Input
                      id="register-auth-method"
                      data-testid="register-auth-method"
                      value={registerAuthMethod}
                      onChange={(e) => setRegisterAuthMethod(e.target.value)}
                      placeholder="hmac"
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="register-action-contract">action_contract（JSON object）</Label>
                    <Textarea
                      id="register-action-contract"
                      data-testid="register-action-contract"
                      value={registerActionContract}
                      onChange={(e) => setRegisterActionContract(e.target.value)}
                      rows={3}
                    />
                  </div>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      data-testid="register-has-credential-binding"
                      checked={registerHasCredential}
                      onChange={(e) => setRegisterHasCredential(e.target.checked)}
                    />
                    has_credential_binding（占位，无明文）
                  </label>
                  <MutateOnly>
                    <Button data-testid="register-connector" onClick={registerConnector}>
                      注册（API-162）
                    </Button>
                  </MutateOnly>
                  {registerSuccess ? (
                    <Alert>
                      <AlertDescription>
                        连接器已登记。列表出现 ≠ 健康绿 ≠ 出站已通 ≠ 已触发 TestRun。
                      </AlertDescription>
                    </Alert>
                  ) : null}
                  {registerError ? (
                    <UndevelopedCallout apis={PAGE_APIS.P25} error={registerError} action="注册连接器 API-162" />
                  ) : null}
                </CardContent>
              </Card>
            ) : null}
            {connectorItems.length === 0 ? (
              <EmptyState title="无组织级连接器" />
            ) : (
              <div className="flex flex-col gap-2">
                {connectorItems.map((item, index) => {
                  const id = String(item.id ?? index);
                  return (
                    <Card key={id}>
                      <CardContent className="flex items-center justify-between p-4">
                        <div className="flex flex-col gap-1">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold">{String(item.name ?? id)}</span>
                            <StatusBadge status={String(item.type ?? "")} />
                            {item.outbound_write_enabled === true ? <Badge variant="success">可写</Badge> : <Badge variant="outline">只读</Badge>}
                          </div>
                          <p className="text-xs text-muted-foreground">
                            credential_present={String(item.credential_present ?? false)} · secret 永不返回 · 出站写入须审批放行
                          </p>
                        </div>
                        <Button size="sm" variant="outline" onClick={() => setSelectedConnector(id)}>
                          查看投递
                        </Button>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
            {canWriteConnector && connectorItems.length > 0 ? (
              <Card className="mt-4">
                <CardHeader>
                  <CardTitle>更新连接器（API-163）</CardTitle>
                </CardHeader>
                <CardContent className="flex max-w-lg flex-col gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="update-connector">连接器</Label>
                    <select
                      id="update-connector"
                      data-testid="update-connector"
                      className="rounded-md border px-3 py-2 text-sm"
                      value={updateTargetId}
                      onChange={(e) => setUpdateConnectorId(e.target.value)}
                    >
                      {connectorItems.map((item, index) => {
                        const id = String(item.id ?? index);
                        return (
                          <option key={id} value={id}>
                            {String(item.name ?? id)} (v{item.version})
                          </option>
                        );
                      })}
                    </select>
                  </div>
                  {updateTarget ? (
                    <>
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="update-name">名称</Label>
                        <Input
                          id="update-name"
                          data-testid="update-name"
                          value={updateName}
                          onChange={(e) => setUpdateName(e.target.value)}
                        />
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="update-action-contract">action_contract（JSON object）</Label>
                        <Textarea
                          id="update-action-contract"
                          data-testid="update-action-contract"
                          value={updateActionContract}
                          onChange={(e) => setUpdateActionContract(e.target.value)}
                          rows={3}
                        />
                      </div>
                      {updateTarget.outbound_write_enabled === true ? (
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            data-testid="update-disable-outbound"
                            checked={updateDisableOutbound}
                            onChange={(e) => setUpdateDisableOutbound(e.target.checked)}
                          />
                          收紧 outbound_write_enabled（true→false）
                        </label>
                      ) : (
                        <p className="text-xs text-muted-foreground">
                          outbound 已关闭。放开可写须走能力恢复审批（API-199），本表单禁止 false→true。
                        </p>
                      )}
                      <MutateOnly>
                        <Button data-testid="update-connector-submit" onClick={updateConnector}>
                          更新（API-163）
                        </Button>
                      </MutateOnly>
                    </>
                  ) : null}
                  {updateSuccess ? (
                    <Alert>
                      <AlertDescription>
                        连接器已更新。列表刷新 ≠ 健康绿 ≠ 出站已通 ≠ 已触发 TestRun。
                      </AlertDescription>
                    </Alert>
                  ) : null}
                  {updateError ? (
                    <UndevelopedCallout apis={PAGE_APIS.P25} error={updateError} action="更新连接器 API-163" />
                  ) : null}
                </CardContent>
              </Card>
            ) : null}
          </TabsContent>
          <TabsContent value="webhooks">
            {deliveries.error ? (
              <UndevelopedCallout apis={PAGE_APIS.P25} error={deliveries.error} action="Webhook 投递 API-164" />
            ) : deliveryItems.length === 0 ? (
              <EmptyState title="无投递记录" hint={connectorId ? `connector ${connectorId}` : "先选择连接器"} />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>投递 ID</TableHead>
                    <TableHead>来源</TableHead>
                    <TableHead>observation_key</TableHead>
                    <TableHead>accepted</TableHead>
                    <TableHead>data_classification</TableHead>
                    <TableHead>验签</TableHead>
                    <TableHead>时间</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {deliveryItems.map((item, index) => (
                    <TableRow key={String(item.id ?? index)}>
                      <TableCell className="font-mono text-xs">{String(item.id ?? "")}</TableCell>
                      <TableCell className="text-xs">{String(item.source ?? "")}</TableCell>
                      <TableCell className="max-w-[12rem] truncate font-mono text-xs">
                        {String(item.observation_key ?? "")}
                      </TableCell>
                      <TableCell className="text-xs">{String(item.accepted ?? item.signature_ok ?? "")}</TableCell>
                      <TableCell className="text-xs">{String(item.data_classification ?? "")}</TableCell>
                      <TableCell>
                        <StatusBadge status={item.signature_ok === true ? "SUCCEEDED" : "FAILED"} />
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">{String(item.observed_at ?? "")}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </TabsContent>
          <TabsContent value="outbound" forceMount>
            <Card>
              <CardHeader>
                <CardTitle>出站通知渠道（主备容灾）</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <Alert>
                  <AlertTitle>配置 ≠ 投递</AlertTitle>
                  <AlertDescription>
                    配置成功不等于通知已投递。站内通知中心属 G4 未做；主备由服务端投影，前端不推演。
                  </AlertDescription>
                </Alert>
                {connectorItems.length === 0 ? (
                  <EmptyState title="无组织级连接器" />
                ) : (
                  <>
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="outbound-connector">连接器</Label>
                      <select
                        id="outbound-connector"
                        className="rounded-md border px-3 py-2 text-sm"
                        value={outboundId}
                        onChange={(e) => {
                          setOutboundConnectorId(e.target.value);
                          setOutboundDraft([]);
                          setOutboundClearArmed(false);
                        }}
                      >
                        {connectorItems.map((item, index) => {
                          const id = String(item.id ?? index);
                          return (
                            <option key={id} value={id}>
                              {String(item.name ?? id)} ({String(item.type ?? "")})
                            </option>
                          );
                        })}
                      </select>
                    </div>
                    {outboundChannels.error ? (
                      <UndevelopedCallout
                        apis={PAGE_APIS.P25}
                        error={outboundChannels.error}
                        action="出站渠道 API-165"
                      />
                    ) : outboundChannels.isPending ? (
                      <p className="text-sm text-muted-foreground">加载渠道配置…</p>
                    ) : outboundItems.length === 0 ? (
                      <EmptyState title="无出站渠道" hint="保存后将写入服务端配置" />
                    ) : (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>channel_type</TableHead>
                            <TableHead>is_primary</TableHead>
                            <TableHead>endpoint_present</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {outboundItems.map((item, index) => (
                            <TableRow key={String(item.id ?? index)}>
                              <TableCell className="text-xs">{item.channel_type}</TableCell>
                              <TableCell className="text-xs">{String(item.is_primary)}</TableCell>
                              <TableCell className="text-xs" data-testid="endpoint-present">
                                {String(item.endpoint_present)}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    )}
                    <div className="flex flex-col gap-2 rounded-md border p-3">
                      <p className="text-xs text-muted-foreground">
                        GET 不返回 endpoint_ref。改配必须重新填写 env:KEY，禁止从服务端列表回填 PUT。空草稿不会保存。
                      </p>
                      {outboundDraft.map((item, index) => (
                        <div key={index} className="grid gap-2 md:grid-cols-3">
                          <Input
                            aria-label="kind"
                            placeholder="kind"
                            value={item.kind}
                            onChange={(e) => {
                              const next = [...outboundDraft];
                              next[index] = { ...item, kind: e.target.value };
                              setOutboundDraft(next);
                            }}
                          />
                          <label className="flex items-center gap-2 text-sm">
                            <input
                              type="checkbox"
                              checked={item.is_primary}
                              onChange={(e) => {
                                const next = [...outboundDraft];
                                next[index] = { ...item, is_primary: e.target.checked };
                                setOutboundDraft(next);
                              }}
                            />
                            is_primary
                          </label>
                          <Input
                            aria-label="endpoint_ref"
                            placeholder="env:KEY"
                            value={item.endpoint_ref ?? ""}
                            onChange={(e) => {
                              const next = [...outboundDraft];
                              next[index] = { ...item, endpoint_ref: e.target.value };
                              setOutboundDraft(next);
                            }}
                          />
                        </div>
                      ))}
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            setOutboundDraft((prev) => [
                              ...prev,
                              { kind: "", is_primary: prev.length === 0, endpoint_ref: "" },
                            ])
                          }
                        >
                          新增草稿行
                        </Button>
                        <MutateOnly>
                          <Button
                            data-testid="save-outbound-channels"
                            size="sm"
                            disabled={!canSaveOutboundDraft}
                            onClick={saveOutboundChannels}
                          >
                            保存（API-166）
                          </Button>
                        </MutateOnly>
                        <MutateOnly>
                          <Button
                            data-testid="clear-outbound-channels"
                            size="sm"
                            variant="destructive"
                            disabled={!outboundId}
                            onClick={clearOutboundChannels}
                          >
                            {outboundClearArmed ? "确认清空渠道" : "清空渠道"}
                          </Button>
                        </MutateOnly>
                      </div>
                    </div>
                    {outboundSaveError ? (
                      <UndevelopedCallout apis={PAGE_APIS.P25} error={outboundSaveError} action="保存出站渠道 API-166" />
                    ) : null}
                  </>
                )}
              </CardContent>
            </Card>
          </TabsContent>
          <TabsContent value="tokens" forceMount>
            <Card>
              <CardHeader>
                <CardTitle>签发 ApiToken</CardTitle>
              </CardHeader>
              <CardContent className="flex max-w-lg flex-col gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="token-name">名称（可选，服务端可忽略）</Label>
                  <Input id="token-name" value={tokenName} onChange={(e) => setTokenName(e.target.value)} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>scopes（至少 read）</Label>
                  <div className="flex flex-wrap gap-2">
                    {API_TOKEN_SCOPES.map((scope) => (
                      <label key={scope} className="flex items-center gap-1 text-sm">
                        <input
                          type="checkbox"
                          checked={selectedScopes.includes(scope)}
                          onChange={() => toggleScope(scope)}
                        />
                        {scope}
                      </label>
                    ))}
                  </div>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="token-expires">到期时间（必填）</Label>
                  <Input
                    id="token-expires"
                    type="datetime-local"
                    value={expiresAtLocal}
                    onChange={(e) => setExpiresAtLocal(e.target.value)}
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  项目白名单：{projectIds.join(", ") || "无项目成员资格，无法签发"}
                </p>
                <MutateOnly>
                  <Button
                    data-testid="issue-api-token"
                    onClick={issueToken}
                    disabled={!canIssue || !expiresAtLocal}
                  >
                    签发（API-171）
                  </Button>
                </MutateOnly>
                {issuedToken ? (
                  <Alert variant="warning">
                    <AlertTitle>一次性明文</AlertTitle>
                    <AlertDescription className="font-mono text-xs">{issuedToken}</AlertDescription>
                  </Alert>
                ) : null}
                {issueError ? <UndevelopedCallout apis={PAGE_APIS.P25} error={issueError} action="签发 Token API-171" /> : null}
              </CardContent>
            </Card>
            {tokenItems.length === 0 ? (
              <EmptyState title="无 Token" />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>前缀</TableHead>
                    <TableHead>scopes</TableHead>
                    <TableHead>到期</TableHead>
                    <TableHead>最近使用</TableHead>
                    <TableHead>吊销</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tokenItems.map((item) => {
                    const id = item.id;
                    return (
                      <TableRow key={id}>
                        <TableCell className="font-mono text-xs">{item.token_prefix}</TableCell>
                        <TableCell className="text-xs">{item.scopes.join(", ")}</TableCell>
                        <TableCell className="text-xs">{item.expires_at}</TableCell>
                        <TableCell className="text-xs">{item.last_used_at ?? "—"}</TableCell>
                        <TableCell className="text-xs">{item.revoked_at ?? "—"}</TableCell>
                        <TableCell>
                          {item.revoked_at ? null : (
                            <MutateOnly>
                              <Button size="sm" variant="destructive" onClick={() => revoke(id)}>
                                吊销
                              </Button>
                            </MutateOnly>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
            {revokeError ? <UndevelopedCallout apis={PAGE_APIS.P25} error={revokeError} action="吊销 API-172" /> : null}
          </TabsContent>
        </Tabs>
      </QueryGate>
    </>
  );
}
