import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import type { ListEnvelope } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { PageHeader, QueryGate } from "@/components/domain/PageState";

export function AssistantPage() {
  const query = useQuery({
    queryKey: ["copilot-sessions"],
    queryFn: () => api.get<ListEnvelope<Record<string, unknown>>>("API-190", "/api/v1/copilot-sessions"),
  });

  return (
    <>
      <PageHeader
        title="Copilot 对话（M3+，入口已从导航隐藏）"
        description="会话（服务端持久化）· 引用展示 · 技能选择 · AI 降级横幅"
      />
      <Alert>
        <AlertTitle>里程碑未开放</AlertTitle>
        <AlertDescription>
          P18 为 M3+ 能力，一级导航按里程碑隐藏本入口。契约存在（API-190），实现可延后；前端不伪造会话。
        </AlertDescription>
      </Alert>
      <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P18}>
        <p className="text-sm text-muted-foreground">会话列表将在后端就绪后渲染，不含消息正文。</p>
      </QueryGate>
    </>
  );
}
