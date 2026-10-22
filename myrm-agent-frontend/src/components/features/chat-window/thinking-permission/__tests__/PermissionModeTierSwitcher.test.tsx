import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import PermissionModeTierSwitcher from '../PermissionModeTierSwitcher';
import { usePermissionTierStore } from '../usePermissionTierStore';

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

  it('toggles dropdown menu on click and lists all 3 tiers with descriptions', () => {
    render(<PermissionModeTierSwitcher />);

    const trigger = screen.getByTestId('permission-tier-trigger');
    fireEvent.click(trigger);

    const menu = screen.getByTestId('permission-tier-menu');
    expect(menu).toBeDefined();

    expect(screen.getByTestId('permission-option-strict')).toBeDefined();
    expect(screen.getByTestId('permission-option-semi-auto')).toBeDefined();
    expect(screen.getByTestId('permission-option-full-auto')).toBeDefined();
    expect(screen.getByText('自动放行常规代码编辑与安全命令，高危命令强制拦截审批')).toBeDefined();
  });

  it('switches to semi-auto mode when option is clicked', () => {
    render(<PermissionModeTierSwitcher />);

    const trigger = screen.getByTestId('permission-tier-trigger');
    fireEvent.click(trigger);

    const semiAutoOption = screen.getByTestId('permission-option-semi-auto');
    fireEvent.click(semiAutoOption);

    expect(usePermissionTierStore.getState().tier).toBe('semi-auto');
    expect(screen.queryByTestId('permission-tier-menu')).toBeNull();
    expect(screen.getByText('半自动敏捷')).toBeDefined();
  });

  it('does not open menu when disabled is true', () => {
    render(<PermissionModeTierSwitcher disabled={true} />);

    const trigger = screen.getByTestId('permission-tier-trigger');
    fireEvent.click(trigger);

    expect(screen.queryByTestId('permission-tier-menu')).toBeNull();
  });
});
