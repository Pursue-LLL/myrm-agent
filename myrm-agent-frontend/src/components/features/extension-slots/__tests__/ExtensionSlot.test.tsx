import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ExtensionSlot } from '../ExtensionSlot';
import { useExtensionSlotStore } from '../useExtensionSlotStore';

describe('ExtensionSlot', () => {
  beforeEach(() => {
    useExtensionSlotStore.setState({ contributions: [] });
  });

  it('renders nothing when no contributions exist and no fallback is provided', () => {
    const { container } = render(<ExtensionSlot name="sidebar.footer.action" />);
    expect(container.firstChild).toBeNull();
  });

  it('renders fallback when no contributions exist', () => {
    render(
      <ExtensionSlot
        name="sidebar.footer.action"
        fallback={<div data-testid="fallback">Empty Slot</div>}
      />,
    );
    expect(screen.getByTestId('fallback')).toHaveTextContent('Empty Slot');
  });

  it('renders registered contributions in order', () => {
    const SlotItemA = () => <div data-testid="item-a">Item A</div>;
    const SlotItemB = () => <div data-testid="item-b">Item B</div>;

    useExtensionSlotStore.getState().registerContribution({
      id: 'item-b',
      slotName: 'sidebar.footer.action',
      order: 20,
      component: SlotItemB,
    });

    useExtensionSlotStore.getState().registerContribution({
      id: 'item-a',
      slotName: 'sidebar.footer.action',
      order: 10,
      component: SlotItemA,
    });

    render(<ExtensionSlot name="sidebar.footer.action" />);

    expect(screen.getByTestId('item-a')).toBeInTheDocument();
    expect(screen.getByTestId('item-b')).toBeInTheDocument();

    const slotContainer = screen.getByTestId('item-a').parentElement;
    expect(slotContainer?.children[0]).toHaveAttribute('data-testid', 'item-a');
    expect(slotContainer?.children[1]).toHaveAttribute('data-testid', 'item-b');
  });

  it('evaluates condition before rendering contribution', () => {
    const VisibleItem = () => <div data-testid="visible">Visible</div>;
    const HiddenItem = () => <div data-testid="hidden">Hidden</div>;

    useExtensionSlotStore.getState().registerContribution({
      id: 'visible-item',
      slotName: 'chat.header.actions',
      component: VisibleItem,
      condition: () => true,
    });

    useExtensionSlotStore.getState().registerContribution({
      id: 'hidden-item',
      slotName: 'chat.header.actions',
      component: HiddenItem,
      condition: () => false,
    });

    render(<ExtensionSlot name="chat.header.actions" />);

    expect(screen.getByTestId('visible')).toBeInTheDocument();
    expect(screen.queryByTestId('hidden')).not.toBeInTheDocument();
  });

  it('supports unregistering contributions', () => {
    const Item = () => <div data-testid="removable">Removable</div>;

    const unregister = useExtensionSlotStore.getState().registerContribution({
      id: 'removable-item',
      slotName: 'navbar.bottom.tools',
      component: Item,
    });

    const { rerender } = render(<ExtensionSlot name="navbar.bottom.tools" />);
    expect(screen.getByTestId('removable')).toBeInTheDocument();

    unregister();
    rerender(<ExtensionSlot name="navbar.bottom.tools" />);
    expect(screen.queryByTestId('removable')).not.toBeInTheDocument();
  });
});
