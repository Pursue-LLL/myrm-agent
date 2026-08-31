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
    render(
      <ExtensionSlot
        name="sidebar.footer.action"
        fallback={<div data-testid="fallback-node">Empty Fallback</div>}
      />,
    );

    expect(screen.getByTestId('fallback-node')).toBeInTheDocument();
  });

  it('renders contributions matching slot name ordered correctly', () => {
    const ComponentA = () => <div data-testid="comp-a">Comp A (order 20)</div>;
    const ComponentB = () => <div data-testid="comp-b">Comp B (order 10)</div>;

    useExtensionSlotStore.getState().registerContribution({
      id: 'test-a',
      slotName: 'sidebar.footer.action',
      order: 20,
      component: ComponentA,
    });

    useExtensionSlotStore.getState().registerContribution({
      id: 'test-b',
      slotName: 'sidebar.footer.action',
      order: 10,
      component: ComponentB,
    });

    const { container } = render(<ExtensionSlot name="sidebar.footer.action" />);

    expect(screen.getByTestId('comp-a')).toBeInTheDocument();
    expect(screen.getByTestId('comp-b')).toBeInTheDocument();

    const items = container.querySelectorAll('[data-testid^="comp-"]');
    expect(items[0]).toHaveAttribute('data-testid', 'comp-b');
    expect(items[1]).toHaveAttribute('data-testid', 'comp-a');
  });

  it('respects dynamic condition evaluation', () => {
    const ActiveComp = () => <div data-testid="comp-active">Active</div>;
    const InactiveComp = () => <div data-testid="comp-inactive">Inactive</div>;

    useExtensionSlotStore.getState().registerContribution({
      id: 'active',
      slotName: 'navbar.bottom.tools',
      component: ActiveComp,
      condition: () => true,
    });

    useExtensionSlotStore.getState().registerContribution({
      id: 'inactive',
      slotName: 'navbar.bottom.tools',
      component: InactiveComp,
      condition: () => false,
    });

    render(<ExtensionSlot name="navbar.bottom.tools" />);

    expect(screen.getByTestId('comp-active')).toBeInTheDocument();
    expect(screen.queryByTestId('comp-inactive')).not.toBeInTheDocument();
  });
});
