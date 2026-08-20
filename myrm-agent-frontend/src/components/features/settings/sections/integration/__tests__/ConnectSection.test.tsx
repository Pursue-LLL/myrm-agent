/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ConnectSection from '../ConnectSection';
import type { ConnectorStatus } from '@/services/connect';

const listConnectorStatusMock = vi.hoisted(() => vi.fn());
const runConnectDoctorMock = vi.hoisted(() => vi.fn());
const generateConnectConfigMock = vi.hoisted(() => vi.fn());
const revokeConnectMock = vi.hoisted(() => vi.fn());
const toastSuccessMock = vi.hoisted(() => vi.fn());
const toastWarningMock = vi.hoisted(() => vi.fn());
const toastErrorMock = vi.hoisted(() => vi.fn());

const TRANSLATIONS: Record<string, string> = {
  title: 'Connections',
  description: 'Connect external agents',
  'status.ready': 'Ready',
  'status.manual_config_required': 'Manual config',
  'status.missing': 'Not connected',
  doctorStatusUnknown: 'Not checked',
  doctorStatusOk: 'Healthy',
  doctorStatusWarn: 'Partially verified',
  doctorStatusFail: 'Check failed',
  doctorLastChecked: 'Checked {time}',
  generate: 'Generate',
  regenerate: 'Regenerate',
  doctor: 'Doctor',
  revoke: 'Revoke',
  copied: 'Copied',
  generateFailed: 'Generate failed',
  doctorFailed: 'Doctor failed',
  revoked: 'Revoked',
  revokeFailed: 'Revoke failed',
  configReady: 'configReady',
  configReadyDesc: 'configReadyDesc',
  configFile: 'configFile',
  token: 'token',
  copy: 'Copy',
  tokenWarning: 'tokenWarning',
  close: 'Close',
  regenerateConfirm: 'regenerateConfirm',
  revokeConfirm: 'revokeConfirm',
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
  useLocale: () => 'en',
}));

vi.mock('@/services/connect', () => ({
  listConnectorStatus: listConnectorStatusMock,
  generateConnectConfig: generateConnectConfigMock,
  runConnectDoctor: runConnectDoctorMock,
  revokeConnect: revokeConnectMock,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: { success: toastSuccessMock, warning: toastWarningMock, error: toastErrorMock },
}));

vi.mock('@/lib/utils/clipboardUtils', () => ({
  writeToClipboard: vi.fn(),
}));

const CONNECTOR: ConnectorStatus = {
  profile_id: 'cursor',
  label: 'Cursor',
  status: 'ready',
  agent_id: 'default',
  doctor_ok: true,
  last_doctor_detail: 'verified',
  connected_at: '2026-08-01T00:00:00Z',
  last_doctor_at: '2026-08-15T10:00:00Z',
};

async function renderSection(overrides: Partial<ConnectorStatus> = {}) {
  listConnectorStatusMock.mockResolvedValue([{ ...CONNECTOR, ...overrides }]);
  const view = render(<ConnectSection />);
  await screen.findByText('Cursor');
  return view;
}

describe('ConnectSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    generateConnectConfigMock.mockResolvedValue({
      profile_id: 'cursor',
      agent_id: 'default',
      mcp_url: 'http://127.0.0.1:8080/mcp',
      token: 'cfg_tok',
      config_json: {},
      instructions: 'Add to cursor',
    });
    revokeConnectMock.mockResolvedValue({ profile_id: 'cursor', revoked: true, trees_removed: 0 });
  });

  it('renders the connector card with its status badge', async () => {
    await renderSection();
    expect(screen.getByText('Cursor')).toBeInTheDocument();
    expect(screen.getByText('Ready')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Doctor' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Regenerate' })).toBeInTheDocument();
  });

  it('renders a grey dot and unknown label before any check ran', async () => {
    const view = await renderSection({ doctor_ok: false, last_doctor_detail: '', last_doctor_at: null });
    expect(view.container.querySelector('span.bg-muted-foreground\\/40')).not.toBeNull();
    expect(screen.getByText('Not checked')).toBeInTheDocument();
  });

  it('renders a green dot and healthy label for a verified check', async () => {
    const view = await renderSection({ doctor_ok: true, last_doctor_detail: 'verified' });
    expect(view.container.querySelector('span.bg-emerald-500')).not.toBeNull();
    expect(screen.getByText('Healthy')).toBeInTheDocument();
  });

  it('renders an amber dot and warn label for a token_env blind spot', async () => {
    const view = await renderSection({ doctor_ok: false, last_doctor_detail: 'token_env' });
    expect(view.container.querySelector('span.bg-amber-500')).not.toBeNull();
    expect(screen.getByText('Partially verified')).toBeInTheDocument();
  });

  it('renders a red dot and fail label for a failed check', async () => {
    const view = await renderSection({ doctor_ok: false, last_doctor_detail: 'token_mismatch' });
    expect(view.container.querySelector('span.bg-red-500')).not.toBeNull();
    expect(screen.getByText('Check failed')).toBeInTheDocument();
  });

  it('shows a success toast when the doctor check passes', async () => {
    runConnectDoctorMock.mockResolvedValue({ profile_id: 'cursor', healthy: true, detail: 'verified', severity: 'ok' });
    await renderSection();
    fireEvent.click(screen.getByRole('button', { name: 'Doctor' }));
    await waitFor(() => expect(toastSuccessMock).toHaveBeenCalledWith('doctorHealthyVerified'));
  });

  it('shows a warning toast for a warn-level blind spot', async () => {
    runConnectDoctorMock.mockResolvedValue({
      profile_id: 'cursor',
      healthy: false,
      detail: 'token_env',
      severity: 'warn',
    });
    await renderSection();
    fireEvent.click(screen.getByRole('button', { name: 'Doctor' }));
    await waitFor(() => expect(toastWarningMock).toHaveBeenCalledWith('doctorDetailTokenEnv'));
  });

  it('shows an error toast with a regenerate action when the check fails', async () => {
    runConnectDoctorMock.mockResolvedValue({
      profile_id: 'cursor',
      healthy: false,
      detail: 'token_mismatch',
      severity: 'error',
    });
    await renderSection();
    fireEvent.click(screen.getByRole('button', { name: 'Doctor' }));
    await waitFor(() =>
      expect(toastErrorMock).toHaveBeenCalledWith(
        'doctorDetailTokenMismatch',
        expect.objectContaining({
          action: expect.objectContaining({ label: 'Regenerate' }),
        }),
      ),
    );
  });

  it('shows a doctorFailed toast when the doctor API rejects', async () => {
    runConnectDoctorMock.mockRejectedValue(new Error('boom'));
    await renderSection();
    fireEvent.click(screen.getByRole('button', { name: 'Doctor' }));
    await waitFor(() => expect(toastErrorMock).toHaveBeenCalledWith('Doctor failed'));
  });
});
