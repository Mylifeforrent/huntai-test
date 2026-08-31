import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState } from "./PageState";

export function EvidenceViewer({
  screenshotUrl,
  videoUrl,
  traceAvailable,
}: {
  screenshotUrl?: string;
  videoUrl?: string;
  traceAvailable?: boolean;
}) {
  return (
    <Tabs defaultValue="screenshot">
      <TabsList>
        <TabsTrigger value="screenshot">截图</TabsTrigger>
        <TabsTrigger value="video">视频</TabsTrigger>
        <TabsTrigger value="trace">Trace</TabsTrigger>
      </TabsList>
      <TabsContent value="screenshot">
        {screenshotUrl ? (
          <img src={screenshotUrl} alt="失败步骤截图" className="max-h-96 rounded-md border" />
        ) : (
          <EmptyState compact title="无截图" hint="需 API-220/221 制品代理" />
        )}
      </TabsContent>
      <TabsContent value="video">
        {videoUrl ? (
          <video src={videoUrl} controls className="max-h-96 w-full rounded-md border" />
        ) : (
          <EmptyState compact title="无视频" hint="需制品授权后由后端代理" />
        )}
      </TabsContent>
      <TabsContent value="trace">
        {traceAvailable ? (
          <p className="text-sm">Trace 回放控件（Playwright trace）</p>
        ) : (
          <EmptyState compact title="Trace 回放不可用" hint="失败步骤应 100% 可回放；当前无制品" />
        )}
      </TabsContent>
    </Tabs>
  );
}
