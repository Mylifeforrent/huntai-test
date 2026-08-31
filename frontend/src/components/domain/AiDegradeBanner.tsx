import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

export function AiDegradeBanner({ active, scope }: { active: boolean; scope?: string }) {
  if (!active) {
    return null;
  }
  return (
    <Alert variant="warning">
      <AlertTitle>AI 降级中</AlertTitle>
      <AlertDescription>
        {scope ?? "AI 增强（归因 / 建议）降级中，当前为规则聚类。平台执行、报告与门禁入口不受影响。"}
      </AlertDescription>
    </Alert>
  );
}
