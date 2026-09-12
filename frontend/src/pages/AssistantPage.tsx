import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { newIdempotencyKey } from "@/api/apiConfig";
import { PAGE_APIS } from "@/api/catalog";
import { queryKeys } from "@/api/queryKeys";
import type { ListEnvelope, ResourceEnvelope } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { CommandFeedback, MutateOnly, PageHeader, QueryGate, EmptyState } from "@/components/domain/PageState";
import { cn } from "@/lib/utils";

interface CopilotSessionItem {
  id: string;
  title?: string | null;
  updated_at?: string;
  project_id?: string | null;
}

interface A6Answer {
  answer: string;
  citations: Array<{ source_type: string; resource_id: string; evidence_ref?: string | null }>;
  tool_calls: Array<{ tool: string; args_hash: string; result_summary: string }>;
  refused_policies: string[];
  meta?: Record<string, unknown>;
}

export function AssistantPage() {
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [projectId, setProjectId] = useState("");
  const [question, setQuestion] = useState("");
  const [lastAnswer, setLastAnswer] = useState<A6Answer | null>(null);
  const [sendError, setSendError] = useState<unknown>(null);

  const list = useQuery({
    queryKey: queryKeys.copilotSessions,
    queryFn: () =>
      api.get<ListEnvelope<CopilotSessionItem>>("API-190", "/api/v1/copilot-sessions"),
  });
  const items = list.data?.data.items ?? [];
  const current = items.find((item) => item.id === sessionId) ?? items[0];

  const detail = useQuery({
    queryKey: ["copilot-sessions", current?.id, "detail"],
    enabled: Boolean(current?.id),
    queryFn: () =>
      api.get<ResourceEnvelope<Record<string, unknown>>>(
        "API-193",
        `/api/v1/copilot-sessions/${current?.id}`,
      ),
  });
  const messages = Array.isArray(detail.data?.data.messages)
    ? (detail.data.data.messages as Array<Record<string, unknown>>)
    : [];

  const createMutation = useMutation({
    mutationFn: () =>
      api.post<ResourceEnvelope<CopilotSessionItem>>(
        "API-191",
        "/api/v1/copilot-sessions",
        {
          title: "Copilot 会话",
          ...(projectId ? { project_id: projectId } : {}),
        },
        newIdempotencyKey(),
      ),
    onSuccess: (payload) => {
      setSessionId(String(payload.data.id ?? ""));
      void queryClient.invalidateQueries({ queryKey: queryKeys.copilotSessions });
    },
  });

  const messageMutation = useMutation({
    mutationFn: () =>
      api.post<ResourceEnvelope<A6Answer>>(
        "API-192",
        `/api/v1/copilot-sessions/${current?.id}/messages`,
        { content: question },
        newIdempotencyKey(),
      ),
    onMutate: () => setSendError(null),
    onSuccess: (payload) => {
      setLastAnswer(payload.data);
      setQuestion("");
      void queryClient.invalidateQueries({ queryKey: ["copilot-sessions", current?.id, "detail"] });
    },
    onError: (error) => setSendError(error),
  });

  return (
    <>
      <PageHeader
        title="Copilot 对话"
        description="服务端会话 · 只读技能 · 引用展示 · 越权阻断（refused_policies）"
      />
      <Alert>
        <AlertTitle>只读助手</AlertTitle>
        <AlertDescription>
          仅提供只读查询能力，工具白名单外一律拒绝。AI 回答由服务端校验引用；越权引用被剥离并记入
          refused_policies。kill switch 关停后提问命令将直接失败。
        </AlertDescription>
      </Alert>
      <CommandFeedback error={sendError} apis={PAGE_APIS.P18} action="Copilot 提问（API-192）" />
      <div className="flex flex-wrap items-end gap-2">
        <Input
          placeholder="项目 ID（权限上下文锚点，可选）"
          value={projectId}
          onChange={(event) => setProjectId(event.target.value)}
          className="max-w-xs"
        />
        <MutateOnly>
          <Button
            onClick={() => createMutation.mutate()}
            disabled={createMutation.isPending}
          >
            新建会话（API-191）
          </Button>
        </MutateOnly>
      </div>
      <QueryGate isPending={list.isPending} error={list.error} apis={PAGE_APIS.P18}>
        {items.length === 0 ? (
          <EmptyState title="无 Copilot 会话" />
        ) : (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[16rem_1fr]">
            <div className="flex flex-col gap-2">
              {items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSessionId(item.id)}
                  className={cn(
                    "rounded-md border p-3 text-left",
                    (sessionId ?? current?.id) === item.id ? "border-primary bg-accent" : "",
                  )}
                >
                  <p className="text-sm">{String(item.title ?? item.id.slice(0, 8))}</p>
                  {item.project_id ? (
                    <p className="font-mono text-xs text-muted-foreground">
                      项目 {String(item.project_id).slice(0, 8)}
                    </p>
                  ) : null}
                </button>
              ))}
            </div>
            <div className="flex flex-col gap-4">
              <Card>
                <CardHeader>
                  <CardTitle>提问（API-192）</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-2">
                  <Textarea
                    rows={3}
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    placeholder="例如：当前项目最近的 TestRun 情况如何？"
                  />
                  <MutateOnly>
                    <Button
                      onClick={() => messageMutation.mutate()}
                      disabled={messageMutation.isPending || !question.trim() || !current?.id}
                    >
                      发送
                    </Button>
                  </MutateOnly>
                </CardContent>
              </Card>
              {lastAnswer ? (
                <Card>
                  <CardHeader>
                    <CardTitle>A6 回答</CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-2 text-sm">
                    <p>{lastAnswer.answer}</p>
                    <div className="flex flex-wrap gap-1">
                      {lastAnswer.citations.map((citation, index) => (
                        <Badge key={index} variant="outline">
                          {citation.source_type}:{String(citation.resource_id).slice(0, 8)}
                        </Badge>
                      ))}
                    </div>
                    {lastAnswer.refused_policies.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {lastAnswer.refused_policies.map((policy, index) => (
                          <Badge key={index} variant="destructive">
                            {policy}
                          </Badge>
                        ))}
                      </div>
                    ) : null}
                  </CardContent>
                </Card>
              ) : null}
              <Card>
                <CardHeader>
                  <CardTitle>会话记录（服务端持久化，最小化）</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-2 text-sm">
                  {messages.length === 0 ? (
                    <p className="text-muted-foreground">暂无消息。</p>
                  ) : (
                    messages.map((message, index) => (
                      <div key={index} className="rounded-md border p-2">
                        <Badge variant={message.role === "user" ? "secondary" : "default"}>
                          {String(message.role ?? "")}
                        </Badge>
                        <p className="mt-1 break-all">{String(message.content ?? "")}</p>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </QueryGate>
    </>
  );
}