/**
 * [INPUT]: @/components/features/extension-slots::ExtensionSlot, useExtensionSlotStore
 * [OUTPUT]: Unit tests for ExtensionSlot rendering and contribution lifecycle
 * [POS]: 声明式扩展插槽单元测试，覆盖动态注册、排序、条件判断、注销与 fallback 渲染。
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { ExtensionSlot } from '../ExtensionSlot';
import { useExtensionSlotStore } from '../useExtensionSlotStore';

describe('ExtensionSlot', () => {
  beforeEach(() => {
    // Reset store
    useExtensionSlotStore.setState({ contributions: [] });
  });

  it('renders fallback when no contributions registered', () => {
    render(<ExtensionSlot name="sidebar.footer.action" fallback={<div data-testid="fallback">No Extensions</div>} />);

    expect(screen.getByTestId('fallback')).toBeInTheDocument();
    expect(screen.getByText('No Extensions')).toBeInTheDocument();
  });

  it('renders nothing when empty and no fallback provided', () => {
    const { container } = render(<ExtensionSlot name="sidebar.footer.action" />);
    expect(container.firstChild).toBeNull();
  });

  it('renders registered contributions sorted by order', () => {
    const ComponentA = () => <div data-testid="item-a">Extension A</div>;
    const ComponentB = () => <div data-testid="item-b">Extension B</div>;

    useExtensionSlotStore.getState().registerContribution({
      id: 'ext-b',
      slotName: 'sidebar.footer.action',
      order: 20,
      component: ComponentB,
    });

    useExtensionSlotStore.getState().registerContribution({
      id: 'ext-a',
      slotName: 'sidebar.footer.action',
      order: 10,
      component: ComponentA,
    });

    render(<ExtensionSlot name="sidebar.footer.action" />);

    expect(screen.getByTestId('item-a')).toBeInTheDocument();
    expect(screen.getByTestId('item-b')).toBeInTheDocument();

    const items = screen.getAllByTestId(/^item-/);
    expect(items[0]).toHaveAttribute('data-testid', 'item-a');
    expect(items[1]).toHaveAttribute('data-testid', 'item-b');
  });

  it('evaluates condition before rendering', () => {
    const ActiveComponent = () => <div data-testid="active">Active</div>;
    const InactiveComponent = () => <div data-testid="inactive">Inactive</div>;

    useExtensionSlotStore.getState().registerContribution({
      id: 'active-item',
      slotName: 'sidebar.footer.action',
      component: ActiveComponent,
      condition: () => true,
    });

    useExtensionSlotStore.getState().registerContribution({
      id: 'inactive-item',
      slotName: 'sidebar.footer.action',
      component: InactiveComponent,
      condition: () => false,
    });

    render(<ExtensionSlot name="sidebar.footer.action" />);

    expect(screen.getByTestId('active')).toBeInTheDocument();
    expect(screen.queryByTestId('inactive')).not.toBeInTheDocument();
  });

  it('supports unregistering contributions', () => {
    const Comp = () => <div data-testid="removable">Removable</div>;

    const unregister = useExtensionSlotStore.getState().registerContribution({
      id: 'temp-item',
      slotName: 'navbar.bottom.tools',
      component: Comp,
    });

    const { rerender } = render(<ExtensionSlot name="navbar.bottom.tools" />);
    expect(screen.getByTestId('removable')).toBeInTheDocument();

    unregister();

    rerender(<ExtensionSlot name="navbar.bottom.tools" />);
    expect(screen.queryByTestId('removable')).not.toBeInTheDocument();
  });
});
