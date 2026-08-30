import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { ExtensionSlot } from '../ExtensionSlot';
import { useExtensionSlotStore } from '../useExtensionSlotStore';

describe('ExtensionSlot Component & Store', () => {
  beforeEach(() => {
    useExtensionSlotStore.setState({ contributions: [] });
  });

  it('renders fallback when no contributions exist for given slot', () => {
    render(
      <ExtensionSlot
        name="sidebar.footer.action"
        fallback={<div data-testid="fallback">No Extensions</div>}
      />,
    );

    expect(screen.getByTestId('fallback')).toBeInTheDocument();
    expect(screen.getByText('No Extensions')).toBeInTheDocument();
  });

  it('renders registered contributions in correct order', () => {
    const TestComponentA = () => <span data-testid="ext-a">Item A</span>;
    const TestComponentB = () => <span data-testid="ext-b">Item B</span>;

    useExtensionSlotStore.getState().registerContribution({
      id: 'item-b',
      slotName: 'sidebar.footer.action',
      order: 20,
      component: TestComponentB,
    });

    useExtensionSlotStore.getState().registerContribution({
      id: 'item-a',
      slotName: 'sidebar.footer.action',
      order: 10,
      component: TestComponentA,
    });

    const { container } = render(<ExtensionSlot name="sidebar.footer.action" />);

    expect(screen.getByTestId('ext-a')).toBeInTheDocument();
    expect(screen.getByTestId('ext-b')).toBeInTheDocument();

    const items = container.querySelectorAll('[data-testid^="ext-"]');
    expect(items[0].getAttribute('data-testid')).toBe('ext-a');
    expect(items[1].getAttribute('data-testid')).toBe('ext-b');
  });

  it('filters out contributions when condition returns false', () => {
    const ActiveComponent = () => <span data-testid="active">Active</span>;
    const InactiveComponent = () => <span data-testid="inactive">Inactive</span>;

    useExtensionSlotStore.getState().registerContribution({
      id: 'active-item',
      slotName: 'navbar.bottom.tools',
      component: ActiveComponent,
      condition: () => true,
    });

    useExtensionSlotStore.getState().registerContribution({
      id: 'inactive-item',
      slotName: 'navbar.bottom.tools',
      component: InactiveComponent,
      condition: () => false,
    });

    render(<ExtensionSlot name="navbar.bottom.tools" />);

    expect(screen.getByTestId('active')).toBeInTheDocument();
    expect(screen.queryByTestId('inactive')).not.toBeInTheDocument();
  });

  it('unregisters contribution cleanly using returned unsubscribe callback', () => {
    const TestComponent = () => <span>Dynamic Item</span>;

    const unregister = useExtensionSlotStore.getState().registerContribution({
      id: 'dynamic-1',
      slotName: 'chat.header.actions',
      component: TestComponent,
    });

    const { rerender } = render(<ExtensionSlot name="chat.header.actions" />);
    expect(screen.getByText('Dynamic Item')).toBeInTheDocument();

    unregister();

    rerender(<ExtensionSlot name="chat.header.actions" fallback={<div>Empty</div>} />);
    expect(screen.queryByText('Dynamic Item')).not.toBeInTheDocument();
    expect(screen.getByText('Empty')).toBeInTheDocument();
  });
});
