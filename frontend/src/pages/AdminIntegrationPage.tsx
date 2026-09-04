import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type {
  ApiTokenIssued,
  ApiTokenListItem,
  ApiTokenScope,
  ConnectorListItem,
  ListEnvelope,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { StatusBadge } from "@/components/domain/StatusBadge";
import { UndevelopedCallout } from "@/components/domain/UndevelopedCallout";
import { useSession } from "@/hooks/useSession";

export function AdminIntegrationPage() {
  const queryClient = useQueryClient();
  const session = useSession();
  const memberships = session.me?.memberships ?? [];
  const projectIds = memberships.map((m) => m.project_id);
  const canIssue = projectIds.length > 0;

  const [issuedToken, setIssuedToken] = useState<string | null>(null);
  const [tokenName, setTokenName] = useState("");
  const [selectedScopes, setSelectedScopes] = useState<ApiTokenScope[]>(["read"]);
  const [expiresAtLocal, setExpiresAtLocal] = useState("");
  const [issueError, setIssueError] = useState<unknown>(null);
  const [revokeError, setRevokeError] = useState<unknown>(null);
  const [selectedConnector, setSelectedConnector] = useState("");

  const connectors = useQuery({
    queryKey: queryKeys.connectors({ scope: "org" }),
    queryFn: () => api.get<ListEnvelope<ConnectorListItem>>("API-160", "/api/v1/connectors"),
  });
  const tokens = useQuery({
    queryKey: queryKeys.apiTokens,
    queryFn: () => api.get<ListEnvelope<ApiTokenListItem>>("API-170", "/api/v1/api-tokens"),
  });
  const connectorId = selectedConnector || String(connectors.data?.data.items[0]?.id ?? "");
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
  const tokenItems = tokens.data?.data.items ?? [];
  const deliveryItems = deliveries.data?.data.items ?? [];
  const pageError = connectors.error ?? tokens.error;

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
            <TabsTrigger value="outbound">出站渠道</TabsTrigger>
            <TabsTrigger value="tokens" data-testid="integration-tab-tokens">ApiToken</TabsTrigger>
          </TabsList>
          <TabsContent value="connectors">
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
          <TabsContent value="outbound">
            <Card>
              <CardHeader>
                <CardTitle>出站通知渠道（主备容灾）</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {connectorItems.filter((item) => item.outbound_write_enabled === true).length === 0 ? (
                  <p className="text-sm text-muted-foreground">无已启用出站写入的连接器。主备由连接器配置投影，不在前端推演。</p>
                ) : (
                  connectorItems
                    .filter((item) => item.outbound_write_enabled === true)
                    .map((item, index) => (
                      <div key={String(item.id ?? index)} className="flex items-center justify-between rounded-md border p-3">
                        <span className="text-sm">{String(item.name ?? "")}</span>
                        <Badge variant="outline">{String(item.type ?? "")}</Badge>
                      </div>
                    ))
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
                <Button
                  data-testid="issue-api-token"
                  onClick={issueToken}
                  disabled={!canIssue || !expiresAtLocal}
                >
                  签发（API-171）
                </Button>
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
                        <TableCell className="text-xs">{item.revoked_at ?? "—"}</TableCell>
                        <TableCell>
                          {item.revoked_at ? null : (
                            <Button size="sm" variant="destructive" onClick={() => revoke(id)}>
                              吊销
                            </Button>
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
