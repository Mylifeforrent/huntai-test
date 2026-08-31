import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { PAGE_APIS } from "@/api/catalog";
import type { ListEnvelope } from "@/api/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { PageHeader, QueryGate } from "@/components/domain/PageState";

export function SkillsPage() {
  const query = useQuery({
    queryKey: ["skills"],
    queryFn: () => api.get<ListEnvelope<Record<string, unknown>>>("API-194", "/api/v1/skills"),
  });

  return (
    <>
      <PageHeader
        title="技能管理（M4，入口已从导航隐藏）"
        description="版本列表 · 三级发布审核 · 金标准测试集结果"
      />
      <Alert>
        <AlertTitle>里程碑未开放</AlertTitle>
        <AlertDescription>
          P19 为 M4 能力，导航入口按里程碑隐藏。未版本化技能不进生产。前端不伪造技能目录。
        </AlertDescription>
      </Alert>
      <QueryGate isPending={query.isPending} error={query.error} apis={PAGE_APIS.P19}>
        <p className="text-sm text-muted-foreground">技能列表将在后端就绪后渲染。完整 instructions 不在列表默认返回。</p>
      </QueryGate>
    </>
  );
}
