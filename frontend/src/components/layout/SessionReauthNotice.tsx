import { useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { currentReturnPath, handleReauth } from "@/api/session";

interface SessionReauthNoticeProps {
  active: boolean;
}

/**
 * Step-up (L3+) re-authentication notice, driven by API-006's `reauth_required`.
 *
 * The server owns the decision and the window length (still TBD in the contract),
 * so this component renders a boolean and never computes an expiry threshold.
 */
export function SessionReauthNotice({ active }: SessionReauthNoticeProps) {
  const [busy, setBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!active) {
    return null;
  }

  async function reauthenticate(): Promise<void> {
    setBusy(true);
    setErrorMessage(null);
    try {
      await handleReauth(currentReturnPath());
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "无法启动再认证");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Alert>
      <AlertTitle>需要重新认证</AlertTitle>
      <AlertDescription className="flex flex-col gap-3">
        <span>
          本次会话已超出再认证窗口。浏览不受影响，但涉及高风险副作用的操作需要先通过企业账号重新认证。
        </span>
        {errorMessage ? <span>{errorMessage}</span> : null}
        <Button size="sm" disabled={busy} onClick={() => void reauthenticate()}>
          重新认证
        </Button>
      </AlertDescription>
    </Alert>
  );
}
