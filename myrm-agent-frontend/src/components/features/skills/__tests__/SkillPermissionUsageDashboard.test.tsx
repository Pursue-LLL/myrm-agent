/** @vitest-environment jsdom */

import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SkillPermissionUsageDashboard } from '../SkillPermissionUsageDashboard';

const toastMock = vi.hoisted(() => vi.fn());

const fetchMock = vi.hoisted(() => vi.fn());

const TRANSLATIONS: Record<string, string> = {
  error: 'error',
  loadFailed: 'loadFailed',
  loading: 'loading',
  noData: 'noData',
  title: 'Permission Usage',
  totalOps: 'ops',
  allowed: 'allowed',
  denied: 'denied',
  successRate: 'successRate',
  last1day: '1d',
  last7days: '7d',
  last30days: '30d',
  last90days: '90d',
  highDenialRate: 'highDenialRate',
  recentOps: 'recentOps',
  total: 'total',
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

describe('SkillPermissionUsageDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  it('renders noData state when stats is empty', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ skill_id: 's1', skill_name: 'Demo', stats: [], total_operations: 0 }),
    });

    render(<SkillPermissionUsageDashboard skillId="s1" />);

    await waitFor(() => expect(screen.getByText('noData')).toBeInTheDocument());
  });

  it('maps backend snake_case fields and renders stats', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        skill_id: 's1',
        skill_name: 'Demo',
        stats: [
          {
            permission: 'shell_exec',
            total_count: 12,
            allowed_count: 8,
            denied_count: 4,
            recent_operations: [
              {
                permission: 'shell_exec',
                operation: 'rm -rf /tmp/x',
                allowed: false,
                deny_reason: 'skill_boundary.violation',
                used_at: '2026-08-13T00:00:00Z',
              },
            ],
          },
        ],
        total_operations: 12,
      }),
    });

    render(<SkillPermissionUsageDashboard skillId="s1" />);

    // Header stats
    await waitFor(() => expect(screen.getAllByText('12').length).toBeGreaterThan(0));
    expect(screen.getAllByText('8').length).toBeGreaterThan(0);
    expect(screen.getAllByText('4').length).toBeGreaterThan(0);
    expect(screen.getByText(/Demo/)).toBeInTheDocument();

    // Recent operation with deny reason
    expect(screen.getByText('rm -rf /tmp/x')).toBeInTheDocument();
    expect(screen.getByText('skill_boundary.violation')).toBeInTheDocument();
  });

  it('does not crash when recent_operations is present', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        skill_id: 's1',
        skill_name: 'Demo',
        stats: [
          {
            permission: 'file_write',
            total_count: 1,
            allowed_count: 1,
            denied_count: 0,
            recent_operations: [
              {
                permission: 'file_write',
                operation: 'write a.txt',
                allowed: true,
                deny_reason: null,
                used_at: '2026-08-12T00:00:00Z',
              },
            ],
          },
        ],
        total_operations: 1,
      }),
    });

    render(<SkillPermissionUsageDashboard skillId="s1" />);

    await waitFor(() => expect(screen.getByText('write a.txt')).toBeInTheDocument());
  });

  it('requests the usage endpoint with days param', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ skill_id: 's1', skill_name: 'Demo', stats: [], total_operations: 0 }),
    });

    render(<SkillPermissionUsageDashboard skillId="s1" />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/skills/s1/permissions/usage?days=7'));
  });
});
