import { useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import type { StepRunItem } from "@/api/types";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { EmptyState } from "./PageState";

async function loadArtifactBlob(artifactId: string): Promise<Blob> {
  return api.getBlob("API-221", `/api/v1/artifacts/${artifactId}/content`);
}

function useArtifactBlob(artifactId: string | undefined) {
  const [blobUrl, setBlobUrl] = useState<string | undefined>();
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!artifactId) {
      setBlobUrl(undefined);
      setError(null);
      return undefined;
    }
    let active = true;
    let objectUrl: string | undefined;
    setLoading(true);
    void loadArtifactBlob(artifactId)
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setBlobUrl(objectUrl);
        setError(null);
      })
      .catch((cause) => {
        if (!active) return;
        setBlobUrl(undefined);
        setError(cause);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [artifactId]);

  return { blobUrl, error, loading };
}

export function EvidenceViewer({
  screenshotArtifactId,
  videoArtifactId,
  traceArtifactId,
  stepRuns = [],
}: {
  screenshotArtifactId?: string;
  videoArtifactId?: string;
  traceArtifactId?: string;
  stepRuns?: StepRunItem[];
}) {
  const screenshot = useArtifactBlob(screenshotArtifactId);
  const video = useArtifactBlob(videoArtifactId);
  const trace = useArtifactBlob(traceArtifactId);
  const traceSteps = useMemo(
    () => [...stepRuns].sort((a, b) => a.step_index - b.step_index),
    [stepRuns],
  );

  const downloadTrace = async () => {
    if (!traceArtifactId) return;
    const blob = await loadArtifactBlob(traceArtifactId);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "trace.zip";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Tabs defaultValue="screenshot">
      <TabsList>
        <TabsTrigger value="screenshot">截图</TabsTrigger>
        <TabsTrigger value="video">视频</TabsTrigger>
        <TabsTrigger value="trace">Trace</TabsTrigger>
      </TabsList>
      <TabsContent value="screenshot">
        {screenshot.loading ? (
          <p className="text-sm text-muted-foreground">加载截图…</p>
        ) : screenshot.blobUrl ? (
          <img src={screenshot.blobUrl} alt="失败步骤截图" className="max-h-96 rounded-md border" />
        ) : (
          <EmptyState compact title="无截图" hint="需 API-220/221 制品代理" />
        )}
      </TabsContent>
      <TabsContent value="video">
        {video.loading ? (
          <p className="text-sm text-muted-foreground">加载视频…</p>
        ) : video.blobUrl ? (
          <video src={video.blobUrl} controls className="max-h-96 w-full rounded-md border" />
        ) : (
          <EmptyState compact title="无视频" hint="需制品授权后由后端代理" />
        )}
      </TabsContent>
      <TabsContent value="trace">
        {traceArtifactId ? (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" size="sm" variant="outline" onClick={() => void downloadTrace()}>
                下载 Trace ZIP
              </Button>
              {trace.loading ? (
                <span className="text-xs text-muted-foreground">准备回放数据…</span>
              ) : null}
            </div>
            {traceSteps.length === 0 ? (
              <EmptyState compact title="无步骤时间线" hint="API-066 步骤列表为空" />
            ) : (
              <ol className="list-decimal space-y-2 pl-5 text-sm">
                {traceSteps.map((step) => (
                  <li key={step.id}>
                    <span className="font-mono text-xs">#{step.step_index}</span>{" "}
                    {step.is_incomplete ? "（不完整）" : null}
                    {step.observation_ref ? (
                      <span className="ml-2 text-xs text-muted-foreground">含 Trace 引用</span>
                    ) : null}
                  </li>
                ))}
              </ol>
            )}
          </div>
        ) : (
          <EmptyState compact title="Trace 回放不可用" hint="失败步骤应 100% 可回放；当前无制品" />
        )}
      </TabsContent>
    </Tabs>
  );
}
