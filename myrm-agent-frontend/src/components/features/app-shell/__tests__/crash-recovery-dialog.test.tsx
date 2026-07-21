import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import CrashRecoveryDialog from '../crash-recovery-dialog';
import { invokeTauriCommand, tauriBackend } from '@/lib/tauri';
import { open } from '@tauri-apps/plugin-dialog';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/lib/tauri', () => ({
  isTauriEnvironment: () => true,
  invokeTauriCommand: vi.fn(() => Promise.resolve('ok')),
  tauriBackend: { start: vi.fn(() => Promise.resolve('ok')) },
}));

vi.mock('@tauri-apps/plugin-dialog', () => ({
  open: vi.fn(() => Promise.resolve('/tmp/export')),
}));

describe('CrashRecoveryDialog', () => {
  const mockDismiss = vi.fn();
  const invokeTauriCommandMock = vi.mocked(invokeTauriCommand);
  const tauriBackendStartMock = vi.mocked(tauriBackend.start);
  const openDialogMock = vi.mocked(open);

  beforeEach(() => {
    mockDismiss.mockClear();
    invokeTauriCommandMock.mockReset();
    tauriBackendStartMock.mockReset();
    openDialogMock.mockReset();
    invokeTauriCommandMock.mockResolvedValue('ok');
    tauriBackendStartMock.mockResolvedValue('ok');
    openDialogMock.mockResolvedValue('/tmp/export');
  });

  it('renders nothing when visible is false', () => {
    const { container } = render(
      <CrashRecoveryDialog visible={false} onDismiss={mockDismiss} />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders dialog when visible is true', () => {
    render(<CrashRecoveryDialog visible={true} onDismiss={mockDismiss} />);
    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.getByText('description')).toBeInTheDocument();
  });

  it('displays error message when provided', () => {
    render(
      <CrashRecoveryDialog
        visible={true}
        errorMessage="Port 8080 already in use"
        onDismiss={mockDismiss}
      />,
    );
    expect(screen.getByText('Port 8080 already in use')).toBeInTheDocument();
  });

  it('does not display error badge when errorMessage is null', () => {
    render(
      <CrashRecoveryDialog visible={true} errorMessage={null} onDismiss={mockDismiss} />,
    );
    expect(screen.queryByText('Port 8080 already in use')).not.toBeInTheDocument();
  });

  it('renders export, logs, and restart buttons', () => {
    render(<CrashRecoveryDialog visible={true} onDismiss={mockDismiss} />);
    expect(screen.getByText('exportDatabase')).toBeInTheDocument();
    expect(screen.getByText('viewLogs')).toBeInTheDocument();
    expect(screen.getByText('retryStart')).toBeInTheDocument();
  });

  it('issues sensitive action ticket before export command', async () => {
    invokeTauriCommandMock
      .mockResolvedValueOnce('ticket-123')
      .mockResolvedValueOnce('database-exported');

    render(<CrashRecoveryDialog visible={true} onDismiss={mockDismiss} />);
    fireEvent.click(screen.getByText('exportDatabase'));

    await waitFor(() => {
      expect(invokeTauriCommandMock).toHaveBeenNthCalledWith(1, 'issue_sensitive_action_ticket', {
        action: 'export_local_sqlite',
      });
      expect(invokeTauriCommandMock).toHaveBeenNthCalledWith(2, 'export_local_sqlite', {
        targetDir: '/tmp/export',
        actionTicket: 'ticket-123',
      });
    });

    expect(screen.getByText('database-exported')).toBeInTheDocument();
  });

  it('does not issue ticket when export folder selection is canceled', async () => {
    openDialogMock.mockResolvedValueOnce(null);
    render(<CrashRecoveryDialog visible={true} onDismiss={mockDismiss} />);

    fireEvent.click(screen.getByText('exportDatabase'));

    await waitFor(() => {
      expect(invokeTauriCommandMock).not.toHaveBeenCalled();
    });
  });

  it('shows export cancellation error returned by backend confirmation flow', async () => {
    invokeTauriCommandMock
      .mockResolvedValueOnce('ticket-456')
      .mockRejectedValueOnce(new Error('Sensitive action cancelled by user'));

    render(<CrashRecoveryDialog visible={true} onDismiss={mockDismiss} />);
    fireEvent.click(screen.getByText('exportDatabase'));

    await waitFor(() => {
      expect(screen.getByText(/Sensitive action cancelled by user/)).toBeInTheDocument();
    });
  });
});
