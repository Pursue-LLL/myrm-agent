/** @vitest-environment jsdom */

/**
 * [INPUT]
 * - ../DashboardWorkspaceLink::DashboardWorkspaceLink
 * - @/components/features/dashboard-workspace/useDashboardWorkspaceStore::useDashboardWorkspaceStore
 *
 * [OUTPUT]
 * - Tests: the toolbar entry stays hidden until a widget is pinned, then opens the drawer.
 *
 * [POS]
 * The drawer is mounted in ChatWindowSatellites; this entry is the only production caller of
 * `toggleDrawer`, so a regression here makes the whole workspace unreachable again.
 */

import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, expect, it, beforeEach, vi } from 'vitest';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

import { TooltipProvider } from '@/components/primitives/tooltip';
import { useDashboardWorkspaceStore } from '@/components/features/dashboard-workspace/useDashboardWorkspaceStore';
import { DashboardWorkspaceLink } from '../DashboardWorkspaceLink';

const renderLink = () =>
  render(
    <TooltipProvider>
      <DashboardWorkspaceLink />
    </TooltipProvider>,
  );

describe('DashboardWorkspaceLink', () => {
  beforeEach(() => {
    act(() => {
      useDashboardWorkspaceStore.getState().clearAllWidgets();
      useDashboardWorkspaceStore.getState().closeDrawer();
    });
  });

  it('is hidden while nothing is pinned', () => {
    renderLink();

    expect(screen.queryByTestId('dashboard-workspace-link')).toBeNull();
  });

  it('shows the pinned count and opens the drawer', () => {
    act(() => {
      useDashboardWorkspaceStore.getState().pinWidget({ id: 'a1', title: 'Report', language: 'html', content: '<b>x</b>' });
      useDashboardWorkspaceStore.getState().pinWidget({ id: 'a2', title: 'Chart', language: 'svg', content: '<svg/>' });
    });
    renderLink();

    const link = screen.getByTestId('dashboard-workspace-link');
    expect(link.textContent).toContain('2');

    fireEvent.click(link);

    expect(useDashboardWorkspaceStore.getState().isDrawerOpen).toBe(true);
  });

  it('is hidden again once the drawer is open, so the two never overlap', () => {
    act(() => {
      useDashboardWorkspaceStore.getState().pinWidget({ id: 'a1', title: 'Report', language: 'html', content: '<b>x</b>' });
      useDashboardWorkspaceStore.getState().openDrawer();
    });

    renderLink();

    expect(screen.queryByTestId('dashboard-workspace-link')).toBeNull();
  });
});
