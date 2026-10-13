import { getOAuthIssuerSettingsPath } from '@/lib/skills/integrationOAuthDisplay';

export type ReauthToastTranslator = (key: string, values?: Record<string, string>) => string;

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

/** An OAuth account expired; the action opens the settings page that owns that account. */
export function showOAuthReauthRequiredToast(data: Record<string, unknown>, deps: ReauthToastDeps): void {
  const issuer = String(data.issuer ?? 'OAuth');
  const reason = String(data.reason ?? '');
  showReauthToast(
    deps,
    `oauth-reauth-${issuer}`,
    deps.t('oauthReauthRequired', { issuer, reason }),
    getOAuthIssuerSettingsPath(issuer),
  );
}
