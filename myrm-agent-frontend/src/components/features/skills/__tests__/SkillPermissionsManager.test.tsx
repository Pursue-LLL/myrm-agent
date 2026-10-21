/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SkillPermissionsManager } from '../SkillPermissionsManager';

const toastMock = vi.hoisted(() => vi.fn());
const fetchMock = vi.hoisted(() => vi.fn());

const TRANSLATIONS: Record<string, string> = {
  error: 'error',
  loadFailed: 'loadFailed',
  loading: 'loading',
  noSkillsWithPermissions: 'noSkillsWithPermissions',
  title: 'Permission Manager',
  description: 'description',
  bulkRevoke: 'bulkRevoke',
  refresh: 'refresh',
  allGranted: 'allGranted',
  partialGranted: 'partialGranted',
  permissionsRequired: 'permissionsRequired',
  dangerousPermission: 'dangerousPermission',
  permissionGranted: 'permissionGranted',
  permissionRevoked: 'permissionRevoked',
  revokeSuccess: 'revokeSuccess',
  updateFailed: 'updateFailed',
  revokeConfirm: 'revokeConfirm',
  revokeTitle: 'revokeTitle',
  confirmRevoke: 'confirmRevoke',
  cancel: 'cancel',
  expand: 'expand',
  collapse: 'collapse',
};

const stableT = (key: string, values?: Record<string, string | number>): string => {
  let text = TRANSLATIONS[key] ?? key;
  if (values) {
    for (const [k, v] of Object.entries(values)) {
      text = text.replaceAll(`{${k}}`, String(v));
    }
  }
  return text;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: toastMock,
}));

describe('SkillPermissionsManager', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  it('shows empty state when no skill declares permissions', async () => {
    // /available 返回的技能无 required_permissions 时，组件应通过 /permissions 判定
    fetchMock.mockImplementation(async (url: string) => {
      if (url === '/api/v1/skills/available') {
        return { ok: true, json: async () => ({ skills: [{ id: 's1', name: 'Demo' }], total: 1 }) };
      }
      return {
        ok: true,
        json: async () => ({ skill_id: 's1', skill_name: 'Demo', required_permissions: [], granted_permissions: [] }),
      };
    });

    render(<SkillPermissionsManager userId="u1" />);

    await waitFor(() => expect(screen.getByText('noSkillsWithPermissions')).toBeInTheDocument());
  });

  it('lists a skill when its /permissions response declares required permissions', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url === '/api/v1/skills/available') {
        return { ok: true, json: async () => ({ skills: [{ id: 's1', name: 'Demo' }], total: 1 }) };
      }
      return {
        ok: true,
        json: async () => ({
          skill_id: 's1',
          skill_name: 'Demo',
          required_permissions: ['shell_exec', 'file_write'],
          granted_permissions: [{ permission: 'shell_exec', granted_at: '2026-08-01T00:00:00Z' }],
        }),
      };
    });

    render(<SkillPermissionsManager userId="u1" />);

    await waitFor(() => expect(screen.getByText('Demo')).toBeInTheDocument());
    expect(screen.getByText('partialGranted')).toBeInTheDocument();

    // 展开查看权限项
    fireEvent.click(screen.getByRole('button', { name: 'expand' }));
    expect(screen.getByText('types.shellExec.label')).toBeInTheDocument();
    expect(screen.getByText('types.fileWrite.label')).toBeInTheDocument();
  });

  it('grants a permission directly without confirmation dialog', async () => {
    fetchMock.mockImplementation(async (url: string, _init?: RequestInit) => {
      if (url === '/api/v1/skills/available') {
        return { ok: true, json: async () => ({ skills: [{ id: 's1', name: 'Demo' }], total: 1 }) };
      }
      if (url.endsWith('/permissions')) {
        return {
          ok: true,
          json: async () => ({
            skill_id: 's1',
            skill_name: 'Demo',
            required_permissions: ['file_write'],
            granted_permissions: [],
          }),
        };
      }
      return { ok: true, json: async () => ({ success: true }) };
    });

    render(<SkillPermissionsManager userId="u1" />);

    await waitFor(() => expect(screen.getByText('Demo')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'expand' }));

    const switchEl = screen.getByRole('switch');
    fireEvent.click(switchEl);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/skills/s1/permissions/grant',
        expect.objectContaining({ method: 'POST' }),
      ),
    );
  });

  it('opens confirmation dialog before revoking a permission', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url === '/api/v1/skills/available') {
        return { ok: true, json: async () => ({ skills: [{ id: 's1', name: 'Demo' }], total: 1 }) };
      }
      return {
        ok: true,
        json: async () => ({
          skill_id: 's1',
          skill_name: 'Demo',
          required_permissions: ['shell_exec'],
          granted_permissions: [{ permission: 'shell_exec', granted_at: '2026-08-01T00:00:00Z' }],
        }),
      };
    });

    render(<SkillPermissionsManager userId="u1" />);

    await waitFor(() => expect(screen.getByText('Demo')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'expand' }));

    // 切换 Switch 到关闭（revoke）→ 应弹确认对话框，且不立即调 revoke API
    const switchEl = screen.getByRole('switch');
    fireEvent.click(switchEl);

    await waitFor(() => expect(screen.getByText('revokeConfirm')).toBeInTheDocument());
    expect(fetchMock).not.toHaveBeenCalledWith('/api/v1/skills/s1/permissions/revoke', expect.anything());

    // 确认撤销
    fireEvent.click(screen.getByText('confirmRevoke'));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/skills/s1/permissions/revoke',
        expect.objectContaining({ method: 'POST' }),
      ),
    );
  });
});
