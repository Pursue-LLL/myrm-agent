/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { InteractiveSpreadsheetViewer } from '../InteractiveSpreadsheetViewer';
import type { SpreadsheetColumn, SpreadsheetRow } from '@/services/spreadsheet';
import * as spreadsheetService from '@/services/spreadsheet';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, unknown>) => {
    if (params?.count !== undefined) {
      return `${key}:${params.count}`;
    }
    return key;
  },
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconSearch: () => <span data-testid="icon-search" />,
  IconDownload: () => <span data-testid="icon-download" />,
  IconExternalLink: () => <span data-testid="icon-external" />,
  IconX: () => <span data-testid="icon-x" />,
  IconChevronUp: () => <span data-testid="icon-chevron-up" />,
  IconChevronDown: () => <span data-testid="icon-chevron-down" />,
  IconLoader: () => <span data-testid="icon-loader" />,
  IconCheck: () => <span data-testid="icon-check" />,
  IconCopy: () => <span data-testid="icon-copy" />,
}));

describe('InteractiveSpreadsheetViewer component', () => {
  const sampleColumns: SpreadsheetColumn[] = [
    { key: 'team', label: '研发团队', col_type: 'string' },
    { key: 'score', label: '效能评分', col_type: 'number' },
  ];
  const sampleRows: SpreadsheetRow[] = [
    { cells: { team: '执行引擎组', score: 98 } },
    { cells: { team: '控制平面组', score: 92 } },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    if (!HTMLDialogElement.prototype.showModal) {
      HTMLDialogElement.prototype.showModal = function showModalMock(
        this: HTMLDialogElement,
      ) {
        this.open = true;
      };
    }
    if (!HTMLDialogElement.prototype.close) {
      HTMLDialogElement.prototype.close = function closeMock(
        this: HTMLDialogElement,
      ) {
        this.open = false;
      };
    }
  });

  it('renders nothing when controlled isOpen is false', () => {
    const { container } = render(
      <InteractiveSpreadsheetViewer
        isOpen={false}
        title="效能概览"
        columns={sampleColumns}
        rows={sampleRows}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders table headers and rows when controlled isOpen is true', () => {
    render(
      <InteractiveSpreadsheetViewer
        isOpen={true}
        title="研发效能总表"
        columns={sampleColumns}
        rows={sampleRows}
      />,
    );

    expect(screen.getByTestId('interactive-spreadsheet-viewer')).toBeInTheDocument();
    expect(screen.getByText('研发效能总表')).toBeInTheDocument();
    expect(screen.getByText('研发团队')).toBeInTheDocument();
    expect(screen.getByText('效能评分')).toBeInTheDocument();
    expect(screen.getByText('执行引擎组')).toBeInTheDocument();
    expect(screen.getByText('控制平面组')).toBeInTheDocument();
    expect(screen.getAllByText('totalRows:2').length).toBeGreaterThan(0);
  });

  it('switches between publication theme palettes', () => {
    render(
      <InteractiveSpreadsheetViewer
        isOpen={true}
        title="研发效能总表"
        columns={sampleColumns}
        rows={sampleRows}
      />,
    );

    const goldBtn = screen.getByText('themeGold');
    fireEvent.click(goldBtn);
    expect(goldBtn).toHaveClass('font-semibold');
    expect(screen.getByText('dark_gold')).toBeInTheDocument();

    const emeraldBtn = screen.getByText('themeEmerald');
    fireEvent.click(emeraldBtn);
    expect(emeraldBtn).toHaveClass('font-semibold');
    expect(screen.getByText('financial_emerald')).toBeInTheDocument();
  });

  it('filters rows based on search keyword input', () => {
    render(
      <InteractiveSpreadsheetViewer
        isOpen={true}
        title="研发效能总表"
        columns={sampleColumns}
        rows={sampleRows}
      />,
    );

    const searchInput = screen.getByPlaceholderText('searchPlaceholder');
    fireEvent.change(searchInput, { target: { value: '引擎' } });

    expect(screen.getByText('执行引擎组')).toBeInTheDocument();
    expect(screen.queryByText('控制平面组')).not.toBeInTheDocument();
    expect(screen.getByText('filteredRows:1')).toBeInTheDocument();
  });

  it('toggles sorting on column header click', () => {
    render(
      <InteractiveSpreadsheetViewer
        isOpen={true}
        title="研发效能总表"
        columns={sampleColumns}
        rows={sampleRows}
      />,
    );

    const teamHeader = screen.getByText('研发团队');
    // Ascending sort
    fireEvent.click(teamHeader);
    expect(screen.getByTestId('icon-chevron-up')).toBeInTheDocument();

    // Descending sort
    fireEvent.click(teamHeader);
    expect(screen.getByTestId('icon-chevron-down')).toBeInTheDocument();
  });

  it('triggers downloadSpreadsheetAsExcel on export button click', async () => {
    const downloadSpy = vi
      .spyOn(spreadsheetService, 'downloadSpreadsheetAsExcel')
      .mockResolvedValueOnce(undefined);

    render(
      <InteractiveSpreadsheetViewer
        isOpen={true}
        title="研发效能总表"
        columns={sampleColumns}
        rows={sampleRows}
      />,
    );

    const exportBtn = screen.getByText('exportExcel');
    fireEvent.click(exportBtn);

    await waitFor(() => {
      expect(downloadSpy).toHaveBeenCalledWith({
        title: '研发效能总表',
        theme: 'business_navy',
        columns: sampleColumns,
        rows: sampleRows,
      });
    });
  });

  it('opens MultiOfficeSyncModal when sync button clicked', () => {
    render(
      <InteractiveSpreadsheetViewer
        isOpen={true}
        title="研发效能总表"
        columns={sampleColumns}
        rows={sampleRows}
      />,
    );

    const syncBtn = screen.getByText('syncOffice');
    fireEvent.click(syncBtn);

    expect(screen.getByText('syncModalTitle')).toBeInTheDocument();
  });

  it('opens viewer panel upon receiving global myrm:open-spreadsheet-viewer event', async () => {
    render(<InteractiveSpreadsheetViewer />);

    act(() => {
      window.dispatchEvent(
        new CustomEvent('myrm:open-spreadsheet-viewer', {
          detail: {
            title: '全局唤起看板',
            columns: sampleColumns,
            rows: sampleRows,
            defaultTheme: 'tech_slate',
          },
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId('interactive-spreadsheet-viewer')).toBeInTheDocument();
      expect(screen.getByText('全局唤起看板')).toBeInTheDocument();
      expect(screen.getByText('tech_slate')).toBeInTheDocument();
    });
  });
});
