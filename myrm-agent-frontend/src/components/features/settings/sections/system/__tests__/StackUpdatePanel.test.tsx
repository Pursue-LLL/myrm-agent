import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import StackUpdatePanel from '../StackUpdatePanel';
import { saveUpdateReceipt } from '@/lib/update-prefs';

const stableT = (key: string, params?: Record<string, string | number>) => {
  if (!params) {
    return key;
  }
  return `${key}:${Object.values(params).join(',')}`;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconCheck: () => <span data-testid="icon-ok" />,
  IconShield: () => <span data-testid="icon-shield" />,
}));

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => true,
}));

const mockHook = vi.hoisted(() => ({
  phase: 'up_to_date',
  info: null as null | { currentVersion: string; version: string; body: string },
  error: null as null | string,
  check: vi.fn(),
  install: vi.fn(),
}));

vi.mock('@/hooks/tauri/useAppUpdate', () => ({
  useAppUpdate: () => mockHook,
}));

const STATUS_PAYLOAD = {
  server_version: '0.1.0',
  harness_version: '0.9.0',
  latest: { version: 'v0.2.0', published_at: '2026-09-01', url: 'https://example.invalid' },
  fetch_error: null,
  stale: true,
  changelog: { fixed: ['Fix crash', 'Repair login'], other: ['Faster search'], grouped: true },
  git: { behind_count: 3, log: ['abc123 fix thing'] },
  prebuilt: { synced_count: 12 },
  cloud: { state: 'unknown' },
};

const byExactText = (text: string) => (_: string, element: Element | null) =>
  element?.textContent === text && (!element?.children || element.children.length === 0);

describe('StackUpdatePanel', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    mockHook.phase = 'up_to_date';
    mockHook.info = null;
    mockHook.error = null;
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, json: async () => STATUS_PAYLOAD })),
    );
  });

  it('renders three legs with versions and a stale badge', async () => {
    render(<StackUpdatePanel />);
    await waitFor(() => {
      expect(screen.getByText('desktopUpToDate')).toBeTruthy();
    });
    expect(screen.getByText(byExactText('serverRow:0.1.0 · harnessRow:0.9.0'), { selector: 'p' })).toBeTruthy();
    expect(screen.getByText(byExactText('staleBadge:v0.2.0'), { selector: 'span' })).toBeTruthy();
    expect(screen.getByText('changelogFixed')).toBeTruthy();
  });

  it('defers the latest version and shows the deferred hint', async () => {
    render(<StackUpdatePanel />);
    await waitFor(() => {
      expect(screen.getByText('staleBadge:v0.2.0')).toBeTruthy();
    });
    fireEvent.click(screen.getByText('defer:v0.2.0'));
    await waitFor(() => {
      expect(screen.getByText('staleBadge:v0.2.0')).toBeTruthy();
      expect(screen.getByText(byExactText('· deferredHint:v0.2.0'))).toBeTruthy();
    });
  });

  it('shows the one-shot post-update receipt', async () => {
    saveUpdateReceipt({ fromVersion: 'v0.1.0', toVersion: 'v0.2.0', at: 'now' });
    render(<StackUpdatePanel />);
    await waitFor(() => {
      expect(screen.getByText('receipt:v0.1.0,v0.2.0')).toBeTruthy();
    });
  });

  it('shows an honest unknown when the service is unreachable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('down');
      }),
    );
    render(<StackUpdatePanel />);
    await waitFor(() => {
      expect(screen.getByText('webUnknown')).toBeTruthy();
    });
  });

  it('runs the doctor and reports pass', async () => {
    render(<StackUpdatePanel />);
    await waitFor(() => {
      expect(screen.getByText('staleBadge:v0.2.0')).toBeTruthy();
    });
    fireEvent.click(screen.getByText('doctorRun'));
    await waitFor(() => {
      expect(screen.getByText('doctorPass')).toBeTruthy();
    });
  });
});
