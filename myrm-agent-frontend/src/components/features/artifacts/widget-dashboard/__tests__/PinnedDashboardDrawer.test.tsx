import React, { act } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PinnedDashboardDrawer } from '../PinnedDashboardDrawer';
import { usePinnedDashboardStore } from '../usePinnedDashboardStore';

const mockTranslations = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => mockTranslations,
}));

describe('PinnedDashboardDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    usePinnedDashboardStore.getState().clearAllPins();
    usePinnedDashboardStore.getState().setDrawerOpen(false);
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <PinnedDashboardDrawer isOpen={false} onClose={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders empty view when open with no pinned widgets', () => {
    render(
      <PinnedDashboardDrawer isOpen={true} onClose={vi.fn()} />
    );
    expect(screen.getByTestId('pinned-dashboard-drawer')).toBeInTheDocument();
    expect(screen.getByTestId('empty-pinned-view')).toBeInTheDocument();
    expect(screen.getByTestId('pinned-count-badge')).toHaveTextContent('0');
  });

  it('renders pinned widgets cards and handles unpin and clear all', async () => {
    act(() => {
      usePinnedDashboardStore.getState().pinWidget({
        id: 'pin_1',
        artifactId: 'art_101',
        title: 'Sales Dashboard',
        type: 'react',
        content: '<SalesChart />',
        networkPolicy: 'none',
      });
      usePinnedDashboardStore.getState().pinWidget({
        id: 'pin_2',
        artifactId: 'art_102',
        title: 'Log Viewer',
        type: 'code',
        content: 'const log = []',
        networkPolicy: 'restricted',
      });
    });

    render(
      <PinnedDashboardDrawer isOpen={true} onClose={vi.fn()} />
    );

    expect(screen.getByTestId('pinned-count-badge')).toHaveTextContent('2');
    expect(screen.getByText('Sales Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Log Viewer')).toBeInTheDocument();

    // Unpin one widget
    const unpinBtn = screen.getByTestId('unpin-btn-art_101');
    await act(async () => {
      fireEvent.click(unpinBtn);
    });

    expect(usePinnedDashboardStore.getState().pinnedWidgets.length).toBe(1);
    expect(screen.queryByText('Sales Dashboard')).toBeNull();

    // Clear all
    const clearBtn = screen.getByTestId('clear-all-pins-btn');
    await act(async () => {
      fireEvent.click(clearBtn);
    });
    expect(usePinnedDashboardStore.getState().pinnedWidgets.length).toBe(0);
    expect(screen.getByTestId('empty-pinned-view')).toBeInTheDocument();
  });

  it('changes network policy when selection is modified', async () => {
    act(() => {
      usePinnedDashboardStore.getState().pinWidget({
        id: 'pin_1',
        artifactId: 'art_101',
        title: 'Interactive App',
        type: 'html',
        content: '<div>app</div>',
        networkPolicy: 'none',
      });
    });

    render(
      <PinnedDashboardDrawer isOpen={true} onClose={vi.fn()} />
    );

    const select = screen.getByTestId('policy-select-art_101');
    await act(async () => {
      fireEvent.change(select, { target: { value: 'full' } });
    });

    const widget = usePinnedDashboardStore.getState().pinnedWidgets[0];
    expect(widget?.networkPolicy).toBe('full');
  });

  it('triggers onExportPoster and updates activeExportWidget when button is clicked', async () => {
    const onExportMock = vi.fn();
    act(() => {
      usePinnedDashboardStore.getState().pinWidget({
        id: 'pin_1',
        artifactId: 'art_101',
        title: 'Live Canvas',
        type: 'svg',
        content: '<svg></svg>',
        networkPolicy: 'none',
      });
    });

    render(
      <PinnedDashboardDrawer
        isOpen={true}
        onClose={vi.fn()}
        onExportPoster={onExportMock}
      />
    );

    const exportBtn = screen.getByTestId('export-poster-btn-art_101');
    await act(async () => {
      fireEvent.click(exportBtn);
    });

    expect(onExportMock).toHaveBeenCalledTimes(1);
    expect(onExportMock.mock.calls[0][0]?.artifactId).toBe('art_101');
    expect(usePinnedDashboardStore.getState().activeExportWidget?.artifactId).toBe('art_101');
  });

  it('triggers onClose when close button is clicked', async () => {
    const onCloseMock = vi.fn();
    render(
      <PinnedDashboardDrawer isOpen={true} onClose={onCloseMock} />
    );

    const closeBtn = screen.getByTestId('close-drawer-btn');
    await act(async () => {
      fireEvent.click(closeBtn);
    });

    expect(onCloseMock).toHaveBeenCalledTimes(1);
  });
});
