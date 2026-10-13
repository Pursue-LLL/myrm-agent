import { describe, expect, it, vi } from 'vitest';

import {
  showMcpAuthRequiredToast,
  showOAuthReauthRequiredToast,
  type ReauthToastDeps,
} from '@/hooks/globalEvents/reauthToasts';

const t = (key: string, values?: Record<string, string>) => (values ? `${key}:${JSON.stringify(values)}` : key);

function buildDeps() {
  const warning = vi.fn();
  const dismiss = vi.fn();
  const push = vi.fn();
  const notifyIfLeader = vi.fn();
  const deps: ReauthToastDeps = { t, router: { push }, toast: { warning, dismiss }, notifyIfLeader };
  return { deps, warning, dismiss, push, notifyIfLeader };
}

function clickAction(warning: ReturnType<typeof vi.fn>): void {
  const options = warning.mock.calls[0][1] as { action: { onClick: () => void } };
  options.action.onClick();
}

describe('showMcpAuthRequiredToast', () => {
  it('warns for 30s with a per-server id and notifies the leader tab', () => {
    const { deps, warning, notifyIfLeader } = buildDeps();

    showMcpAuthRequiredToast({ server_name: 'notion' }, deps);

    expect(warning).toHaveBeenCalledOnce();
    expect(warning).toHaveBeenCalledWith(
      'mcpAuthRequired:{"server":"notion"}',
      expect.objectContaining({ id: 'mcp-auth-notion', duration: 30_000, dismissible: true }),
    );
    expect(notifyIfLeader).toHaveBeenCalledWith('mcpAuthRequired:{"server":"notion"}');
  });

  it('reauthorizes in the MCP settings and dismisses the toast', () => {
    const { deps, warning, dismiss, push } = buildDeps();

    showMcpAuthRequiredToast({ server_name: 'notion' }, deps);
    clickAction(warning);

    expect(dismiss).toHaveBeenCalledWith('mcp-auth-notion');
    expect(push).toHaveBeenCalledWith('/settings/mcp');
  });

  it('falls back to a generic server name', () => {
    const { deps, warning } = buildDeps();

    showMcpAuthRequiredToast({}, deps);

    expect(warning).toHaveBeenCalledWith(
      'mcpAuthRequired:{"server":"MCP"}',
      expect.objectContaining({ id: 'mcp-auth-MCP' }),
    );
  });
});

describe('showOAuthReauthRequiredToast', () => {
  it('names the account for people while keying the toast by the raw issuer, and never shows the backend reason', () => {
    const { deps, warning, dismiss, push, notifyIfLeader } = buildDeps();

    showOAuthReauthRequiredToast({ issuer: 'google_workspace', reason: 'refresh token revoked' }, deps);

    expect(warning).toHaveBeenCalledWith(
      'oauthReauthRequired:{"issuer":"Google Workspace"}',
      expect.objectContaining({ id: 'oauth-reauth-google_workspace', duration: 30_000, dismissible: true }),
    );
    expect(notifyIfLeader).toHaveBeenCalledOnce();

    clickAction(warning);
    expect(dismiss).toHaveBeenCalledWith('oauth-reauth-google_workspace');
    expect(push).toHaveBeenCalledWith('/settings/credentials');
  });

  it('names the xAI account with its brand spelling and reconnects it under Credentials', () => {
    const { deps, warning, push } = buildDeps();

    showOAuthReauthRequiredToast({ issuer: 'xai', reason: 'expired' }, deps);

    expect(warning).toHaveBeenCalledWith(
      'oauthReauthRequired:{"issuer":"xAI"}',
      expect.objectContaining({ id: 'oauth-reauth-xai' }),
    );
    clickAction(warning);
    expect(push).toHaveBeenCalledWith('/settings/credentials');
  });

  it('falls back to a generic account name', () => {
    const { deps, warning } = buildDeps();

    showOAuthReauthRequiredToast({}, deps);

    expect(warning).toHaveBeenCalledWith(
      'oauthReauthRequired:{"issuer":"OAuth"}',
      expect.objectContaining({ id: 'oauth-reauth-OAuth' }),
    );
  });
});
