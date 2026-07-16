import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import E2EESecurityPanel from '../E2EESecurityPanel';

vi.mock('@/components/primitives/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const baseProps = {
  established: false,
  fingerprint: null,
  algorithm: 'NaCl Box (Curve25519)',
  sessionIdPrefix: null,
  error: null,
};

describe('E2EESecurityPanel', () => {
  it('renders nothing when not established and no error', () => {
    const { container } = render(<E2EESecurityPanel {...baseProps} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders error state with ShieldX icon', () => {
    render(<E2EESecurityPanel {...baseProps} error="Handshake timeout" />);
    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-label', 'handshakeFailed');
    expect(status).toHaveTextContent('handshakeFailed');
    expect(status.classList.contains('text-destructive')).toBe(true);
  });

  it('renders established state with secured badge', () => {
    render(
      <E2EESecurityPanel {...baseProps} established fingerprint="a1b2 c3d4 e5f6 g7h8" sessionIdPrefix="sess1234" />,
    );
    const badge = screen.getByRole('status');
    expect(badge).toHaveAttribute('aria-label', 'secured');
    expect(badge).toHaveTextContent('secured');
  });

  it('displays algorithm and fingerprint in popover content', () => {
    render(
      <E2EESecurityPanel {...baseProps} established fingerprint="a1b2 c3d4 e5f6 g7h8" sessionIdPrefix="sess1234" />,
    );
    expect(screen.getByText('NaCl Box (Curve25519)')).toBeInTheDocument();
    expect(screen.getByText('a1b2 c3d4 e5f6 g7h8')).toBeInTheDocument();
    expect(screen.getByText('sess1234…')).toBeInTheDocument();
  });

  it('hides fingerprint section when fingerprint is null', () => {
    render(<E2EESecurityPanel {...baseProps} established fingerprint={null} sessionIdPrefix={null} />);
    expect(screen.getByText('NaCl Box (Curve25519)')).toBeInTheDocument();
    expect(screen.queryByText('fingerprint')).not.toBeInTheDocument();
    expect(screen.queryByText('sessionId')).not.toBeInTheDocument();
  });

  it('error state takes priority over established', () => {
    render(<E2EESecurityPanel {...baseProps} established fingerprint="a1b2 c3d4 e5f6 g7h8" error="Some error" />);
    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-label', 'handshakeFailed');
  });
});
