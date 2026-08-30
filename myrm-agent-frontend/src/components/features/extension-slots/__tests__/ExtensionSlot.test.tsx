import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { ExtensionSlot } from '../ExtensionSlot';
import { useExtensionSlotStore } from '../useExtensionSlotStore';

describe('ExtensionSlot', () => {
  beforeEach(() => {
    useExtensionSlotStore.setState({ contributions: [] });
  });

  it('renders fallback when no contributions registered', () => {
    render(<ExtensionSlot name="sidebar.footer.action" fallback={<div>Empty Slot</div>} />);
    expect(screen.getByText('Empty Slot')).toBeInTheDocument();
  });

  it('renders registered contributions in order', () => {
    const ComponentA = () => <div>Item A</div>;
    const ComponentB = () => <div>Item B</div>;

    useExtensionSlotStore.getState().registerContribution({
      id: 'item-b',
      slotName: 'sidebar.footer.action',
      order: 20,
      component: ComponentB,
    });

    useExtensionSlotStore.getState().registerContribution({
      id: 'item-a',
      slotName: 'sidebar.footer.action',
      order: 10,
      component: ComponentA,
    });

    render(<ExtensionSlot name="sidebar.footer.action" />);
    const container = screen.getByText('Item A').parentElement;
    expect(screen.getByText('Item A')).toBeInTheDocument();
    expect(screen.getByText('Item B')).toBeInTheDocument();
    expect(container?.textContent).toBe('Item AItem B');
  });

  it('filters out contributions that fail condition', () => {
    const ComponentVisible = () => <div>Visible Item</div>;
    const ComponentHidden = () => <div>Hidden Item</div>;

    useExtensionSlotStore.getState().registerContribution({
      id: 'visible',
      slotName: 'sidebar.footer.action',
      component: ComponentVisible,
      condition: () => true,
    });

    useExtensionSlotStore.getState().registerContribution({
      id: 'hidden',
      slotName: 'sidebar.footer.action',
      component: ComponentHidden,
      condition: () => false,
    });

    render(<ExtensionSlot name="sidebar.footer.action" />);
    expect(screen.getByText('Visible Item')).toBeInTheDocument();
    expect(screen.queryByText('Hidden Item')).not.toBeInTheDocument();
  });

  it('unregisters contributions cleanly', () => {
    const Component = () => <div>Dynamic Item</div>;

    const unregister = useExtensionSlotStore.getState().registerContribution({
      id: 'dyn-item',
      slotName: 'chat.header.actions',
      component: Component,
    });

    const { rerender } = render(
      <ExtensionSlot name="chat.header.actions" fallback={<div>No Items</div>} />,
    );
    expect(screen.getByText('Dynamic Item')).toBeInTheDocument();

    unregister();
    rerender(<ExtensionSlot name="chat.header.actions" fallback={<div>No Items</div>} />);
    expect(screen.queryByText('Dynamic Item')).not.toBeInTheDocument();
    expect(screen.getByText('No Items')).toBeInTheDocument();
  });
});
