import React, { act } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WidgetPosterExportModal } from '../WidgetPosterExportModal';
import type { PinnedWidget } from '../widgetDashboardTypes';

const mockTranslations = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => mockTranslations,
}));

describe('WidgetPosterExportModal', () => {
  const dummyWidget: PinnedWidget = {
    id: 'pin_test',
    artifactId: 'art_test',
    title: 'Financial Analyzer Widget',
    type: 'react',
    content: 'const FinancialAnalyzer = () => { return <div>ROI: 24%</div> }',
    pinnedAt: 1700000000000,
    networkPolicy: 'none',
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when isOpen is false or widget is null', () => {
    const { container: c1 } = render(
      <WidgetPosterExportModal isOpen={false} widget={dummyWidget} onClose={vi.fn()} />
    );
    expect(c1.firstChild).toBeNull();

    const { container: c2 } = render(
      <WidgetPosterExportModal isOpen={true} widget={null} onClose={vi.fn()} />
    );
    expect(c2.firstChild).toBeNull();
  });

  it('renders poster modal with widget metadata and preview stage', () => {
    render(
      <WidgetPosterExportModal isOpen={true} widget={dummyWidget} onClose={vi.fn()} />
    );

    expect(screen.getByTestId('poster-export-dialog')).toBeInTheDocument();
    expect(screen.getByText('Financial Analyzer Widget')).toBeInTheDocument();
    expect(screen.getByText('react')).toBeInTheDocument();
    expect(screen.getByTestId('poster-preview-stage')).toBeInTheDocument();
  });

  it('allows switching between poster themes', async () => {
    render(
      <WidgetPosterExportModal isOpen={true} widget={dummyWidget} onClose={vi.fn()} />
    );

    const emeraldBtn = screen.getByTestId('theme-btn-emerald_pro');
    await act(async () => {
      fireEvent.click(emeraldBtn);
    });

    const stage = screen.getByTestId('poster-preview-stage');
    expect(stage.className).toContain('emerald');

    const sunsetBtn = screen.getByTestId('theme-btn-amber_sunset');
    await act(async () => {
      fireEvent.click(sunsetBtn);
    });
    expect(stage.className).toContain('amber');
  });

  it('copies content summary to clipboard', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(
      <WidgetPosterExportModal isOpen={true} widget={dummyWidget} onClose={vi.fn()} />
    );

    const copyBtn = screen.getByTestId('copy-poster-text-btn');
    await act(async () => {
      fireEvent.click(copyBtn);
    });

    expect(writeTextMock).toHaveBeenCalledTimes(1);
    expect(writeTextMock.mock.calls[0][0]).toContain('Financial Analyzer Widget');
  });

  it('triggers download and callbacks when download poster button is clicked', async () => {
    const onDownloadSuccessMock = vi.fn();
    const createObjectURLMock = vi.fn().mockReturnValue('blob:dummy-url');
    const revokeObjectURLMock = vi.fn();
    window.URL.createObjectURL = createObjectURLMock;
    window.URL.revokeObjectURL = revokeObjectURLMock;

    render(
      <WidgetPosterExportModal
        isOpen={true}
        widget={dummyWidget}
        onClose={vi.fn()}
        onDownloadSuccess={onDownloadSuccessMock}
      />
    );

    const downloadBtn = screen.getByTestId('download-poster-btn');
    await act(async () => {
      fireEvent.click(downloadBtn);
    });

    expect(createObjectURLMock).toHaveBeenCalledTimes(1);
    expect(revokeObjectURLMock).toHaveBeenCalledTimes(1);
    expect(onDownloadSuccessMock).toHaveBeenCalledTimes(1);
  });

  it('triggers onClose when close button is clicked', async () => {
    const onCloseMock = vi.fn();
    render(
      <WidgetPosterExportModal isOpen={true} widget={dummyWidget} onClose={onCloseMock} />
    );

    const closeBtn = screen.getByTestId('close-modal-btn');
    await act(async () => {
      fireEvent.click(closeBtn);
    });

    expect(onCloseMock).toHaveBeenCalledTimes(1);
  });
});
