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
        fallback={<div data-testid="fallback-slot">Empty fallback</div>}
      />,
    );

    expect(screen.getByTestId('fallback-slot')).toBeDefined();
    expect(screen.getByText('Empty fallback')).toBeDefined();
  });

  it('renders registered contributions matching slot name', () => {
    const TestComponentA = () => <div data-testid="contrib-a">Action A</div>;
    const TestComponentB = () => <div data-testid="contrib-b">Action B</div>;

    useExtensionSlotStore.getState().registerContribution({
      id: 'plugin-a',
      slotName: 'sidebar.footer.action',
      order: 10,
      component: TestComponentA,
    });

    useExtensionSlotStore.getState().registerContribution({
      id: 'plugin-b',
      slotName: 'sidebar.footer.action',
      order: 20,
      component: TestComponentB,
    });

    render(<ExtensionSlot name="sidebar.footer.action" />);

    expect(screen.getByTestId('contrib-a')).toBeDefined();
    expect(screen.getByTestId('contrib-b')).toBeDefined();
  });

  it('filters out contributions where condition returns false', () => {
    const TestActive = () => <div data-testid="contrib-active">Active Plugin</div>;
    const TestInactive = () => <div data-testid="contrib-inactive">Inactive Plugin</div>;

    useExtensionSlotStore.getState().registerContribution({
      id: 'active',
      slotName: 'chat.header.actions',
      component: TestActive,
      condition: () => true,
    });

    useExtensionSlotStore.getState().registerContribution({
      id: 'inactive',
      slotName: 'chat.header.actions',
      component: TestInactive,
      condition: () => false,
    });

    render(<ExtensionSlot name="chat.header.actions" />);

    expect(screen.getByTestId('contrib-active')).toBeDefined();
    expect(screen.queryByTestId('contrib-inactive')).toBeNull();
  });

  it('correctly unregisters contribution on cleanup', () => {
    const TestComp = () => <div data-testid="temp-contrib">Temporary</div>;

    const unregister = useExtensionSlotStore.getState().registerContribution({
      id: 'temp',
      slotName: 'navbar.bottom.tools',
      component: TestComp,
    });

    const { rerender } = render(<ExtensionSlot name="navbar.bottom.tools" />);
    expect(screen.getByTestId('temp-contrib')).toBeDefined();

    unregister();
    rerender(<ExtensionSlot name="navbar.bottom.tools" />);
    expect(screen.queryByTestId('temp-contrib')).toBeNull();
  });
});
