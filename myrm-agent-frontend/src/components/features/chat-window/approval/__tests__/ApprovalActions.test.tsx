/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ApprovalActions from '../ApprovalActions';

type Request = Parameters<typeof ApprovalActions>[0]['request'];

function renderActions(overrides: Partial<Parameters<typeof ApprovalActions>[0]> = {}, request: Request = {}) {
  const handlers = {
    onApprove: vi.fn(),
    onEdit: vi.fn(),
    onReject: vi.fn(),
    onAlwaysAllow: vi.fn(),
    onAllowDomain: vi.fn(),
  };
  render(
    <ApprovalActions
      request={request}
      isLoading={false}
      isExpired={false}
      isAutoApproved={false}
      isSaveSkill={false}
      {...handlers}
      {...overrides}
    />,
  );
  return handlers;
}

describe('ApprovalActions', () => {
  it('offers approve, edit, reject and always-allow, each wired to its own callback', () => {
    const handlers = renderActions();

    fireEvent.click(screen.getByText('approve'));
    fireEvent.click(screen.getByText('edit'));
    fireEvent.click(screen.getByText('reject'));
    fireEvent.click(screen.getByText('allowAlways'));

    expect(handlers.onApprove).toHaveBeenCalledTimes(1);
    expect(handlers.onEdit).toHaveBeenCalledTimes(1);
    expect(handlers.onReject).toHaveBeenCalledTimes(1);
    expect(handlers.onAlwaysAllow).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('domain.allowDomain')).toBeNull();
  });

  it('after the smart reviewer refused, only a one-time override and reject remain', () => {
    const handlers = renderActions({}, { smartDenied: true });

    expect(screen.queryByText('edit')).toBeNull();
    expect(screen.queryByText('allowAlways')).toBeNull();
    fireEvent.click(screen.getByText('smartDenied.overrideOnce'));
    fireEvent.click(screen.getByText('reject'));

    expect(handlers.onApprove).toHaveBeenCalledTimes(1);
    expect(handlers.onReject).toHaveBeenCalledTimes(1);
  });

  it('a skill save can only be approved or denied', () => {
    renderActions({ isSaveSkill: true });

    expect(screen.getByText('saveSkill.approve')).toBeTruthy();
    expect(screen.getByText('saveSkill.deny')).toBeTruthy();
    expect(screen.queryByText('edit')).toBeNull();
    expect(screen.queryByText('allowAlways')).toBeNull();
  });

  it('hides always-allow when the request does not allow it', () => {
    renderActions({}, { hideAllowAlways: true });

    expect(screen.queryByText('allowAlways')).toBeNull();
  });

  it('shows the domain shortcut only when the request carries domains to approve', () => {
    const handlers = renderActions({}, { domainApproval: true, domains: ['example.com'] });

    fireEvent.click(screen.getByText('domain.allowDomain'));

    expect(handlers.onAllowDomain).toHaveBeenCalledTimes(1);
  });

  it('keeps reject available after expiry but not approve, edit or always-allow', () => {
    renderActions({ isExpired: true });

    expect((screen.getByText('approve').closest('button') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByText('edit').closest('button') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByText('allowAlways').closest('button') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByText('reject').closest('button') as HTMLButtonElement).disabled).toBe(false);
  });

  it('shows the auto-approving state and blocks a second click while it runs', () => {
    renderActions({ isAutoApproved: true });

    expect((screen.getByText('autoApproving').closest('button') as HTMLButtonElement).disabled).toBe(true);
  });
});
