import { useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { currentReturnPath, startOidcLogin } from "@/api/session";

export function SsoRecoveryPanel() {
  const [busy, setBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function retryWithEnterpriseLogin(): Promise<void> {
    setBusy(true);
    setErrorMessage(null);
    try {
      await startOidcLogin(currentReturnPath(), { prompt: "login" });
    } catch (error) {
      setBusy(false);
      setErrorMessage(error instanceof Error ? error.message : "无法启动企业登录");
    }
  }

  return (
    <Alert>
      <AlertTitle>企业 SSO 未成功</AlertTitle>
      <AlertDescription className="flex flex-col gap-3">
        <span>
          单点登录没有完成。请使用公司账号在企业身份提供商页面再次认证。HuntAI
          不会收集或保存你的密码。
        </span>
        {errorMessage ? <span>{errorMessage}</span> : null}
        <Button size="sm" disabled={busy} onClick={() => void retryWithEnterpriseLogin()}>
          使用企业账号重新登录
        </Button>
      </AlertDescription>
    </Alert>
  );
}
