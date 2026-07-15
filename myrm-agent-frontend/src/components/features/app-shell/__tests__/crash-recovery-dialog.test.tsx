import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import CrashRecoveryDialog from '../crash-recovery-dialog';

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

  beforeEach(() => {
    mockDismiss.mockClear();
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
});
