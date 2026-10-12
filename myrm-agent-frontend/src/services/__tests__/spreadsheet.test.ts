import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from '../api';
import {
  generateStyledExcelBlob,
  downloadSpreadsheetAsExcel,
  syncSpreadsheetToOffice,
  type SpreadsheetGenerateRequest,
  type OfficeSyncRequest,
  type OfficeSyncResponse,
} from '../spreadsheet';

vi.mock('../api', () => ({
  apiClient: {
    post: vi.fn(),
  },
}));

describe('spreadsheet service client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const samplePayload: SpreadsheetGenerateRequest = {
    title: 'Q3 研发预算与效能表',
    theme: 'financial_emerald',
    columns: [
      { key: 'team', label: '团队', col_type: 'string' },
      { key: 'budget', label: '预算', col_type: 'currency' },
    ],
    rows: [
      { cells: { team: '执行引擎', budget: 120 } },
    ],
  };

  it('generateStyledExcelBlob sends POST request to /api/v1/spreadsheet/generate-excel', async () => {
    const mockBlob = new Blob(['mock-binary-data'], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });

    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      blob: vi.fn().mockResolvedValueOnce(mockBlob),
    });
    vi.stubGlobal('fetch', mockFetch);

    const result = await generateStyledExcelBlob(samplePayload);

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/spreadsheet/generate-excel', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(samplePayload),
    });
    expect(result).toEqual(mockBlob);

    vi.unstubAllGlobals();
  });

  it('downloadSpreadsheetAsExcel creates object URL and triggers download', async () => {
    const mockBlob = new Blob(['mock-binary'], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });

    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      blob: vi.fn().mockResolvedValueOnce(mockBlob),
    });
    vi.stubGlobal('fetch', mockFetch);

    const createObjectURLMock = vi.fn().mockReturnValue('blob:http://localhost/test-uuid');
    const revokeObjectURLMock = vi.fn();
    vi.stubGlobal('URL', {
      createObjectURL: createObjectURLMock,
      revokeObjectURL: revokeObjectURLMock,
    });

    const clickSpy = vi.fn();
    const createElementSpy = vi.spyOn(document, 'createElement').mockReturnValue({
      set href(val: string) {},
      set download(val: string) {},
      click: clickSpy,
    } as unknown as HTMLAnchorElement);
    const appendChildSpy = vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);
    const removeChildSpy = vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node);

    await downloadSpreadsheetAsExcel(samplePayload, 'custom_report.xlsx');

    expect(createObjectURLMock).toHaveBeenCalledWith(mockBlob);
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(revokeObjectURLMock).toHaveBeenCalledWith('blob:http://localhost/test-uuid');

    createElementSpy.mockRestore();
    appendChildSpy.mockRestore();
    removeChildSpy.mockRestore();
    vi.unstubAllGlobals();
  });

  it('syncSpreadsheetToOffice sends POST request to /api/v1/spreadsheet/sync-office', async () => {
    const syncRequest: OfficeSyncRequest = {
      platform: 'feishu_bitable',
      table_name: '核心指标看板',
      columns: samplePayload.columns,
      rows: samplePayload.rows,
    };

    const mockResponse: OfficeSyncResponse = {
      platform: 'feishu_bitable',
      success: true,
      sync_id: 'sync_12345',
      url: 'https://feishu.cn/base/sync_12345',
      record_count: 1,
      message: 'Synced 1 records',
    };

    vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

    const result = await syncSpreadsheetToOffice(syncRequest);

    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/spreadsheet/sync-office',
      syncRequest,
    );
    expect(result).toEqual(mockResponse);
  });
});
