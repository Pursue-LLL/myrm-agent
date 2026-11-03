/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const localeRef = vi.hoisted(() => ({ value: 'zh' }));
vi.mock('next-intl', () => ({
  useLocale: () => localeRef.value,
}));

import AuditLogTable from '../AuditLogTable';

const LOG = {
  sequence: 7,
  timestamp: 1_700_000_000,
  command: 'ls -la',
  exit_code: 2,
  stdout: 'listing',
  stderr: 'permission denied',
  duration_ms: 12,
  success: false,
  command_type: 'READ',
  risk_level: 'LOW',
  error_message: 'boom',
};

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ ok: true, json: async () => [LOG] } as unknown as Response)),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function openDetails() {
  await userEvent.click(await screen.findByText('ls -la'));
}

describe('AuditLogTable detail dialog copy', () => {
  it('shows the Chinese side of every detail label for a zh user', async () => {
    localeRef.value = 'zh';
    render(<AuditLogTable />);
    await openDetails();

    expect(screen.getByText(/^退出码: 2 \| 耗时: 12ms$/)).toBeInTheDocument();
    expect(screen.getByText('标准输出:')).toBeInTheDocument();
    expect(screen.getByText('标准错误:')).toBeInTheDocument();
    expect(screen.getByText('错误信息:')).toBeInTheDocument();
    expect(screen.getByText(/序号:/)).toBeInTheDocument();
    expect(screen.queryByText('Standard Output:')).not.toBeInTheDocument();
  });

  it('shows the English side of every detail label for an en user', async () => {
    localeRef.value = 'en';
    render(<AuditLogTable />);
    await openDetails();

    expect(screen.getByText(/^Exit Code: 2 \| Duration: 12ms$/)).toBeInTheDocument();
    expect(screen.getByText('Standard Output:')).toBeInTheDocument();
    expect(screen.getByText('Standard Error:')).toBeInTheDocument();
    expect(screen.getByText('Error Message:')).toBeInTheDocument();
    expect(screen.getByText(/Sequence:/)).toBeInTheDocument();
    expect(screen.queryByText('标准输出:')).not.toBeInTheDocument();
  });
});
