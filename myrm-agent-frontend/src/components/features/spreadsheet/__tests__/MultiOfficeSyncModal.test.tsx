import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MultiOfficeSyncModal } from '../MultiOfficeSyncModal';
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
  IconCheck: () => <span data-testid="icon-check" />,
  IconCopy: () => <span data-testid="icon-copy" />,
  IconExternalLink: () => <span data-testid="icon-external" />,
  IconX: () => <span data-testid="icon-x" />,
  IconLoader: () => <span data-testid="icon-loader" />,
}));

describe('MultiOfficeSyncModal component', () => {
  const sampleColumns: SpreadsheetColumn[] = [
    { key: 'team', label: '团队' },
    { key: 'budget', label: '预算' },
  ];
  const sampleRows: SpreadsheetRow[] = [
    { cells: { team: '执行引擎', budget: 100 } },
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

  it('renders modal with table name and stats when open', () => {
    render(
      <MultiOfficeSyncModal
        isOpen={true}
        onClose={vi.fn()}
        tableName="Q3核算看板"
        columns={sampleColumns}
        rows={sampleRows}
      />,
    );

    expect(screen.getByText('syncModalTitle')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Q3核算看板')).toBeInTheDocument();
    expect(screen.getByText('totalCols:2')).toBeInTheDocument();
    expect(screen.getByText('totalRows:1')).toBeInTheDocument();
  });

  it('allows switching platforms', () => {
    render(
      <MultiOfficeSyncModal
        isOpen={true}
        onClose={vi.fn()}
        tableName="Q3核算看板"
        columns={sampleColumns}
        rows={sampleRows}
      />,
    );

    const wecomButton = screen.getByText('platformWeCom');
    fireEvent.click(wecomButton);
    expect(wecomButton).toHaveClass('border-indigo-500');

    const dingtalkButton = screen.getByText('platformDingTalk');
    fireEvent.click(dingtalkButton);
    expect(dingtalkButton).toHaveClass('border-indigo-500');
  });

  it('submits sync and displays link callout upon success', async () => {
    const mockSyncResponse = {
      platform: 'feishu_bitable' as const,
      success: true,
      sync_id: 'sync_999',
      url: 'https://feishu.cn/base/sync_999',
      record_count: 1,
      message: 'Success',
    };
    vi.spyOn(spreadsheetService, 'syncSpreadsheetToOffice').mockResolvedValueOnce(
      mockSyncResponse,
    );

    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(
      <MultiOfficeSyncModal
        isOpen={true}
        onClose={vi.fn()}
        tableName="Q3核算看板"
        columns={sampleColumns}
        rows={sampleRows}
      />,
    );

    const syncButton = screen.getByText('syncButton');
    act(() => {
      fireEvent.click(syncButton);
    });

    await waitFor(() => {
      expect(spreadsheetService.syncSpreadsheetToOffice).toHaveBeenCalledWith({
        platform: 'feishu_bitable',
        table_name: 'Q3核算看板',
        columns: sampleColumns,
        rows: sampleRows,
      });
      expect(screen.getByText('syncSuccess')).toBeInTheDocument();
      expect(screen.getByText('openInOffice')).toBeInTheDocument();
    });

    const copyBtn = screen.getByText('copyLink');
    fireEvent.click(copyBtn);
    expect(writeTextMock).toHaveBeenCalledWith('https://feishu.cn/base/sync_999');
  });

  it('triggers onClose when close button clicked', () => {
    const onCloseMock = vi.fn();
    render(
      <MultiOfficeSyncModal
        isOpen={true}
        onClose={onCloseMock}
        tableName="Q3核算看板"
        columns={sampleColumns}
        rows={sampleRows}
      />,
    );

    const closeBtn = screen.getAllByRole('button', { name: 'close' })[0];
    if (closeBtn) {
      fireEvent.click(closeBtn);
    }
    expect(onCloseMock).toHaveBeenCalledTimes(1);
  });
});
