import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/domain/PageState";

export function NotFoundPage() {
  return (
    <>
      <PageHeader title="资源不存在" description="跨租户与不可感知资源统一按不存在呈现，不区分 403。" />
      <p className="text-sm text-muted-foreground">当前路径没有对应页面，或目标对象不可见。</p>
      <Button asChild variant="outline">
        <Link to="/">返回工作台</Link>
      </Button>
    </>
  );
}
