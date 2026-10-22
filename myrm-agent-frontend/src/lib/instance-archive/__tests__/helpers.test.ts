import { beforeEach, describe, expect, it, vi } from 'vitest';

const deploy = vi.hoisted(() => ({ tauri: false, remote: false }));
const tauri = vi.hoisted(() => ({ invokeTauriCommand: vi.fn() }));
const api = vi.hoisted(() => ({ apiRequest: vi.fn() }));

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => deploy.tauri,
  isRemoteGatewayActive: () => deploy.remote,
}));
vi.mock('@/lib/tauri', () => tauri);
vi.mock('@/lib/api', () => api);

import en from '../../../../locales/en.json';
import { losesHistory } from '../counts';
import { archiveErrorMessageKey } from '../errors';
import { formatBackupDate } from '../format';
import { reentryGroups } from '../reentry';
import { performRestart, planRestart } from '../restart';

describe('reentryGroups', () => {
  it('groups storage identifiers into stable user-facing categories', () => {
    expect(
      reentryGroups(['table:agent_secrets', 'config:mcpOAuthTokens', 'config:providers', 'config:searchServices']),
    ).toEqual(['modelKeys', 'mcpConnections', 'savedSecrets']);
  });

  it('sends unknown credential rows to connected accounts and never leaks identifiers', () => {
    expect(reentryGroups(['config:telegramCredentials', 'table:something_new'])).toEqual(['connectedAccounts']);
    expect(reentryGroups(['path:.myrm/credentials.json'])).toEqual(['savedSecrets']);
    expect(reentryGroups([])).toEqual([]);
  });

  it('files each sign-in folder under the account or secret it belongs to', () => {
    expect(reentryGroups(['path:whatsapp_auth', 'path:matrix'])).toEqual(['connectedAccounts']);
    expect(reentryGroups(['path:session_vault'])).toEqual(['savedSecrets']);
  });
});

describe('losesHistory', () => {
  it('is true only when the backup holds fewer chats or messages than the app has now', () => {
    expect(losesHistory({ counts: { chats: 5, messages: 100 }, current_counts: { chats: 6, messages: 100 } })).toBe(
      true,
    );
    expect(losesHistory({ counts: { chats: 6, messages: 90 }, current_counts: { chats: 6, messages: 100 } })).toBe(
      true,
    );
    expect(losesHistory({ counts: { chats: 6, messages: 100 }, current_counts: { chats: 6, messages: 100 } })).toBe(
      false,
    );
    expect(losesHistory({ counts: { chats: 9, messages: 900 }, current_counts: { chats: 6, messages: 100 } })).toBe(
      false,
    );
  });

  it('does not guess when the running app could not be read', () => {
    expect(losesHistory({ counts: { chats: 1, messages: 1 }, current_counts: {} })).toBe(false);
  });

  it('ignores other kinds of content', () => {
    expect(losesHistory({ counts: { skills: 1 }, current_counts: { skills: 9, agents: 4 } })).toBe(false);
  });
});

describe('formatBackupDate', () => {
  it('renders a readable local date and degrades to nothing for garbage', () => {
    expect(formatBackupDate('2026-09-13T12:00:00Z', 'en')).toMatch(/Sep 1[23], 2026/);
    expect(formatBackupDate('not-a-date', 'en')).toBe('');
  });
});

describe('archiveErrorMessageKey', () => {
  it('keeps codes with localized copy and degrades everything else to generic', () => {
    expect(archiveErrorMessageKey('newer_schema')).toBe('newer_schema');
    expect(archiveErrorMessageKey('wrong_passphrase')).toBe('wrong_passphrase');
    expect(archiveErrorMessageKey('promotion_failed')).toBe('restore_failed');
    expect(archiveErrorMessageKey('rollback_incomplete')).toBe('rollback_incomplete');
    expect(archiveErrorMessageKey('Traceback: boom')).toBe('generic');
    expect(archiveErrorMessageKey(null)).toBe('generic');
  });

  it('has plain-language copy for every way an automatic backup can be refused or fail', () => {
    const codes = [
      'backup_dir_invalid',
      'backup_dir_inside_state',
      'backup_dir_not_writable',
      'backup_write_failed',
      'backup_unreadable',
      'backup_incomplete',
    ];
    const copy: Record<string, string> = en.instanceArchive.errors;

    for (const code of codes) {
      expect(archiveErrorMessageKey(code)).toBe(code);
      expect(copy[code]).toBeTruthy();
    }
  });
});

describe('restart planning', () => {
  beforeEach(() => {
    deploy.tauri = false;
    deploy.remote = false;
    tauri.invokeTauriCommand.mockReset();
    api.apiRequest.mockReset();
  });

  it('restarts the bundled backend through the desktop shell', async () => {
    deploy.tauri = true;
    expect(planRestart('process')).toBe('desktop');
    await performRestart('desktop');
    expect(tauri.invokeTauriCommand).toHaveBeenCalledWith('restart_app');
  });

  it('does not restart the local app when the desktop talks to a remote backend', () => {
    deploy.tauri = true;
    deploy.remote = true;
    expect(planRestart('process')).toBe('manual');
    expect(planRestart('sandbox')).toBe('sandbox');
  });

  it('recreates sandbox deployments and asks bare local processes to be restarted by hand', async () => {
    expect(planRestart('sandbox')).toBe('sandbox');
    await performRestart('sandbox');
    // No body: only the reset card asks for the Python packages to be cleared; a restart after a restore keeps them.
    expect(api.apiRequest).toHaveBeenCalledWith('/system/sandbox/recreate', { method: 'POST', silent: true });
    expect(planRestart('process')).toBe('manual');
  });
});
