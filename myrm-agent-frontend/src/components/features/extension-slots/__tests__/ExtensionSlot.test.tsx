import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { ExtensionSlot, useExtensionSlotStore } from '../index';

describe('ExtensionSlot Component and Store', () => {
  beforeEach(() => {
    useExtensionSlotStore.setState({ contributions: [] });
  });

  it('renders fallback when no contributions match the slot', () => {
    render(<ExtensionSlot name="navbar.bottom.tools" fallback={<div data-testid="fallback">No items</div>} />);
    expect(screen.getByTestId('fallback')).toBeDefined();
    expect(screen.getByText('No items')).toBeDefined();
  });

  it('renders nothing if slot is empty and no fallback provided', () => {
    const { container } = render(<ExtensionSlot name="navbar.bottom.tools" />);
    expect(container.firstChild).toBeNull();
  });

  it('renders registered contribution for the slot', () => {
    const TestComponent = () => <div data-testid="test-tool">Custom Plugin Button</div>;

    useExtensionSlotStore.getState().registerContribution({
      id: 'plugin-tool-1',
      slotName: 'navbar.bottom.tools',
      component: TestComponent,
    });

    render(<ExtensionSlot name="navbar.bottom.tools" />);
    expect(screen.getByTestId('test-tool')).toBeDefined();
    expect(screen.getByText('Custom Plugin Button')).toBeDefined();
  });

  it('sorts multiple contributions by order', () => {
    const ComponentA = () => <span>First</span>;
    const ComponentB = () => <span>Second</span>;

    useExtensionSlotStore.getState().registerContribution({
      id: 'item-2',
      slotName: 'sidebar.footer.action',
      order: 20,
      component: ComponentB,
    });

    useExtensionSlotStore.getState().registerContribution({
      id: 'item-1',
      slotName: 'sidebar.footer.action',
      order: 10,
      component: ComponentA,
    });

    const { container } = render(<ExtensionSlot name="sidebar.footer.action" />);
    expect(container.textContent).toBe('FirstSecond');
  });

  it('respects condition predicate', () => {
    const ConditionalComponent = () => <div>Only on desktop</div>;

    useExtensionSlotStore.getState().registerContribution({
      id: 'cond-item',
      slotName: 'chat.header.actions',
      component: ConditionalComponent,
      condition: () => false,
    });

    render(<ExtensionSlot name="chat.header.actions" fallback={<div>Hidden Fallback</div>} />);
    expect(screen.queryByText('Only on desktop')).toBeNull();
    expect(screen.getByText('Hidden Fallback')).toBeDefined();
  });

  it('supports unregistering contributions', () => {
    const DisposableComponent = () => <div>Disposable</div>;

    const unregister = useExtensionSlotStore.getState().registerContribution({
      id: 'temp-item',
      slotName: 'navbar.bottom.tools',
      component: DisposableComponent,
    });

    const { rerender } = render(<ExtensionSlot name="navbar.bottom.tools" />);
    expect(screen.getByText('Disposable')).toBeDefined();

    unregister();

    rerender(<ExtensionSlot name="navbar.bottom.tools" fallback={<div>Unregistered</div>} />);
    expect(screen.queryByText('Disposable')).toBeNull();
    expect(screen.getByText('Unregistered')).toBeDefined();
  });
});
