/**
 * [INPUT] '@/lib/skills/integrationOAuthDisplay'::SETTINGS_CREDENTIALS_PATH / formatOAuthIssuerLabel (POS: OAuth 账号的设置页落点与展示名)
 * [OUTPUT] showMcpAuthRequiredToast / showOAuthReauthRequiredToast: 展示「需要重新授权」提示条，操作按钮直达负责该连接的设置页;
 *          ReauthToastDeps: 提示条所需的翻译、路由、toast 与跨标签页通知能力
 * [POS] 全局事件的重新授权提示条。把 MCP / OAuth 授权失效事件变成可点击的 toast，落点与服务端推送深链一致。
 */
import { formatOAuthIssuerLabel, SETTINGS_CREDENTIALS_PATH } from '@/lib/skills/integrationOAuthDisplay';

type ReauthToastTranslator = (key: string, values?: Record<string, string>) => string;

interface ReauthToastOptions {
  id: string;
  duration: number;
  dismissible: boolean;
  action: { label: string; onClick: () => void };
}

export interface ReauthToastDeps {
  t: ReauthToastTranslator;
  router: { push: (href: string) => void };
  toast: {
    warning: (message: string, options: ReauthToastOptions) => void;
    dismiss: (id: string) => void;
  };
  notifyIfLeader: (title: string) => void;
}

const REAUTH_TOAST_DURATION_MS = 30_000;
const MCP_SETTINGS_PATH = '/settings/mcp';

function showReauthToast(deps: ReauthToastDeps, toastId: string, message: string, targetPath: string): void {
  const { t, router, toast } = deps;
  toast.warning(message, {
    id: toastId,
    duration: REAUTH_TOAST_DURATION_MS,
    dismissible: true,
    action: {
      label: t('reauthorize'),
      onClick: () => {
        toast.dismiss(toastId);
        router.push(targetPath);
      },
    },
  });
  deps.notifyIfLeader(message);
}

/** An MCP server needs the user to sign in again; the action opens the MCP settings where it reconnects. */
export function showMcpAuthRequiredToast(data: Record<string, unknown>, deps: ReauthToastDeps): void {
  const serverName = String(data.server_name ?? 'MCP');
  showReauthToast(deps, `mcp-auth-${serverName}`, deps.t('mcpAuthRequired', { server: serverName }), MCP_SETTINGS_PATH);
}

/** An OAuth account expired; the action opens the Credentials page where it reconnects. */
export function showOAuthReauthRequiredToast(data: Record<string, unknown>, deps: ReauthToastDeps): void {
  const issuer = String(data.issuer ?? 'OAuth');
  showReauthToast(
    deps,
    `oauth-reauth-${issuer}`,
    deps.t('oauthReauthRequired', { issuer: formatOAuthIssuerLabel(issuer) }),
    SETTINGS_CREDENTIALS_PATH,
  );
}
