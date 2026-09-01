import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ConnectorListItem, ListEnvelope, WebhookDeliveryItem } from "@/api/types";
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
import { asRecord } from "@/lib/utils";

export function AdminIntegrationPage() {
  const [issueTried, setIssueTried] = useState(false);
  const [revokeTried, setRevokeTried] = useState(false);
  const [issuedToken, setIssuedToken] = useState<string | null>(null);
  const [tokenName, setTokenName] = useState("");
  const [selectedConnector, setSelectedConnector] = useState("");

  const connectors = useQuery({
    queryKey: queryKeys.connectors({ scope: "org" }),
    queryFn: () => api.get<ListEnvelope<ConnectorListItem>>("API-160", "/api/v1/connectors"),
  });
  const tokens = useQuery({
    queryKey: queryKeys.apiTokens,
    queryFn: () => api.get<ListEnvelope<Record<string, unknown>>>("API-170", "/api/v1/api-tokens"),
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

  function issueToken() {
    setIssueTried(true);
    setIssuedToken(null);
    void api
      .post<Record<string, unknown>>("API-171", "/api/v1/api-tokens", {
        name: tokenName,
        scopes: ["read"],
        project_ids: [],
      })
      .then((body) => {
        const data = asRecord(body.data);
        const token = typeof data.token === "string" ? data.token : typeof body.token === "string" ? body.token : null;
        if (token) setIssuedToken(token);
      })
      .catch(() => undefined);
  }

  function revoke(id: string) {
    setRevokeTried(true);
    void api.post("API-172", `/api/v1/api-tokens/${id}/revocations`, {}).catch(() => undefined);
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
            <TabsTrigger value="tokens">ApiToken</TabsTrigger>
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
                            credential_present={String(item.credential_present ?? false)} · secret 永不返回
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
                    <TableHead>验签</TableHead>
                    <TableHead>时间</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {deliveryItems.map((item, index) => (
                    <TableRow key={String(item.id ?? index)}>
                      <TableCell className="font-mono text-xs">{String(item.id ?? "")}</TableCell>
                      <TableCell className="text-xs">{String(item.source ?? "")}</TableCell>
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
          <TabsContent value="tokens">
            <Card>
              <CardHeader>
                <CardTitle>签发 ApiToken</CardTitle>
              </CardHeader>
              <CardContent className="flex max-w-lg flex-col gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="token-name">名称</Label>
                  <Input id="token-name" value={tokenName} onChange={(e) => setTokenName(e.target.value)} />
                </div>
                <Button onClick={issueToken}>签发（API-171）</Button>
                {issuedToken ? (
                  <Alert variant="warning">
                    <AlertTitle>一次性明文</AlertTitle>
                    <AlertDescription className="font-mono text-xs">{issuedToken}</AlertDescription>
                  </Alert>
                ) : null}
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
                  {tokenItems.map((item, index) => {
                    const id = String(item.id ?? index);
                    const scopes = Array.isArray(item.scopes) ? item.scopes.map(String) : [];
                    return (
                      <TableRow key={id}>
                        <TableCell className="font-mono text-xs">{String(item.token_prefix ?? "")}</TableCell>
                        <TableCell className="text-xs">{scopes.join(", ")}</TableCell>
                        <TableCell className="text-xs">{String(item.expires_at ?? "")}</TableCell>
                        <TableCell className="text-xs">{String(item.revoked_at ?? "—")}</TableCell>
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
          </TabsContent>
        </Tabs>
      </QueryGate>
      {issueTried ? <UndevelopedCallout apis={PAGE_APIS.P25} action="签发 Token API-171（明文仅成功响应一次）" /> : null}
      {revokeTried ? <UndevelopedCallout apis={PAGE_APIS.P25} action="吊销 API-172" /> : null}
    </>
  );
}
