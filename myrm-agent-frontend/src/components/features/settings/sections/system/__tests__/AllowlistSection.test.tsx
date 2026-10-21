import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import AllowlistSection from '../AllowlistSection';

const stableAllowlistT = (key: string, values?: Record<string, string | number>) => {
  const dict: Record<string, string> = {
    title: 'Allowlist Records',
    description: 'Tools and permissions allowed without confirmation',
    refresh: 'Refresh',
    clearAll: 'Clear All',
    clearConfirmTitle: 'Clear all allowlist entries?',
    clearConfirmDescription: 'This cannot be undone.',
    timeBound: 'Time-bound',
    permanent: 'Permanent',
    expiresAt: 'Expires at',
    toolName: 'Tool Name',
    argsHash: 'Arguments Hash',
    commandPattern: 'Command Pattern',
    emptyTitle: 'No allowlist records',
    emptyDescription: 'Records added via Always Allow will appear here.',
    'granularities.permission': 'Permission',
    'granularities.tool': 'Tool',
    'granularities.exact': 'Exact Match',
    'granularities.pattern': 'Similar Commands',
  };
  return dict[key] ?? key;
};

vi.mock('next-intl', () => ({
  useLocale: () => 'zh-CN',
  useTranslations: () => stableAllowlistT,
}));

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: vi.fn(),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

describe('AllowlistSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders time-bound badge and expiration timestamp when expires_at is present', async () => {
    const { fetchWithTimeout } = await import('@/lib/api');
    const futureIso = new Date(Date.now() + 3600 * 1000).toISOString();
    vi.mocked(fetchWithTimeout).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        success: true,
        data: [
          {
            id: 'entry-1',
            permission: 'shell_exec',
            tool_name: 'bash_code_execute_tool',
            tool_args_hash: null,
            command_pattern: 'npm test *',
            created_at: new Date().toISOString(),
            expires_at: futureIso,
            granularity: 'pattern',
          },
          {
            id: 'entry-2',
            permission: 'file_read',
            tool_name: 'read_file',
            tool_args_hash: null,
            command_pattern: null,
            created_at: new Date().toISOString(),
            expires_at: null,
            granularity: 'tool',
          },
        ],
      }),
    } as unknown as Response);

    render(<AllowlistSection />);

    await waitFor(() => {
      expect(screen.getByText('Time-bound')).toBeInTheDocument();
      expect(screen.getByText('Permanent')).toBeInTheDocument();
      expect(screen.getByText('npm test *')).toBeInTheDocument();
      expect(screen.getByText(/Expires at/)).toBeInTheDocument();
    });
  });
});
