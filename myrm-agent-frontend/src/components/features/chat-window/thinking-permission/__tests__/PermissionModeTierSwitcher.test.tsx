import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import PermissionModeTierSwitcher from '../PermissionModeTierSwitcher';
import { usePermissionTierStore } from '../usePermissionTierStore';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'zh'));

describe('PermissionModeTierSwitcher', () => {
  beforeEach(() => {
    localStorage.clear();
    usePermissionTierStore.setState({ tier: 'strict' });
  });

  it('renders initial strict mode capsule button', () => {
    render(<PermissionModeTierSwitcher />);

    const trigger = screen.getByTestId('permission-tier-trigger');
    expect(trigger).toBeDefined();
    expect(screen.getByText('安全守护')).toBeDefined();
    expect(screen.queryByTestId('permission-tier-menu')).toBeNull();
  });

  it('opens the menu on click and lists all 3 tiers with descriptions', async () => {
    const user = userEvent.setup();
    render(<PermissionModeTierSwitcher />);

    await user.click(screen.getByTestId('permission-tier-trigger'));

    const menu = await screen.findByTestId('permission-tier-menu');
    expect(screen.getByTestId('permission-option-strict')).toBeDefined();
    expect(screen.getByTestId('permission-option-semi-auto')).toBeDefined();
    expect(screen.getByTestId('permission-option-full-auto')).toBeDefined();
    expect(screen.getByText('自动放行常规代码编辑与安全命令，高危命令强制拦截审批')).toBeDefined();

    // The composer clips inline popups, so the menu must live in a portal outside of it.
    expect(screen.getByTestId('permission-mode-tier-switcher')).not.toContainElement(menu);
  });

  it('marks only the active tier as the checked menu item', async () => {
    const user = userEvent.setup();
    render(<PermissionModeTierSwitcher />);

    await user.click(screen.getByTestId('permission-tier-trigger'));

    expect(await screen.findByTestId('permission-option-strict')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByTestId('permission-option-semi-auto')).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByTestId('permission-option-full-auto')).toHaveAttribute('aria-checked', 'false');
  });

  it('switches to semi-auto mode and closes the menu when an option is chosen', async () => {
    const user = userEvent.setup();
    render(<PermissionModeTierSwitcher />);

    await user.click(screen.getByTestId('permission-tier-trigger'));
    await user.click(await screen.findByTestId('permission-option-semi-auto'));

    expect(usePermissionTierStore.getState().tier).toBe('semi-auto');
    await waitFor(() => expect(screen.queryByTestId('permission-tier-menu')).toBeNull());
    expect(screen.getByText('半自动敏捷')).toBeDefined();
  });

  it('does not open the menu when disabled is true', async () => {
    const user = userEvent.setup();
    render(<PermissionModeTierSwitcher disabled={true} />);

    await user.click(screen.getByTestId('permission-tier-trigger'));

    expect(screen.queryByTestId('permission-tier-menu')).toBeNull();
  });
});
