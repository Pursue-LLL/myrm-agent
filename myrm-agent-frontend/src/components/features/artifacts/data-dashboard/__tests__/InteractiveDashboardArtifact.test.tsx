import React, { act } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { InteractiveDashboardArtifact } from '../InteractiveDashboardArtifact';

const mockTranslations = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => mockTranslations,
}));

describe('InteractiveDashboardArtifact', () => {
  const sampleJsonContent = JSON.stringify({
    title: '全球电商运营监控大盘',
    subtitle: '多维业务与经营指标',
    kpis: [
      { label: 'GMV', value: '$8,420,000', change_pct: 18.5, trend: 'up', detail: '同比 +18.5%' },
      { label: '退货率', value: '2.4%', change_pct: -0.8, trend: 'down', detail: '环比下降' },
    ],
    charts: [
      {
        id: 'gmv_trend',
        title: '月度 GMV 走势',
        chart_type: 'bar',
        x_axis_labels: ['1月', '2月', '3月'],
        series: [{ name: 'GMV', data: [2100000, 2800000, 3520000] }],
        description: '季度业务稳健增长',
      },
    ],
    tables: [
      {
        title: '核心订单明细',
        headers: ['订单号', '地区', '金额', '状态'],
        rows: [
          ['ORD-001', '北美', '$120', '已发货'],
          ['ORD-002', '欧洲', '$350', '已完成'],
          ['ORD-003', '亚太', '$85', '处理中'],
        ],
      },
    ],
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders dashboard with HUD header, KPIs, chart, and data table', () => {
    render(<InteractiveDashboardArtifact content={sampleJsonContent} title="全球电商看板" />);

    expect(screen.getByTestId('interactive-dashboard-artifact-root')).toBeInTheDocument();
    expect(screen.getByText('全球电商运营监控大盘')).toBeInTheDocument();
    expect(screen.getByText('GMV')).toBeInTheDocument();
    expect(screen.getByText('$8,420,000')).toBeInTheDocument();
    expect(screen.getByText('退货率')).toBeInTheDocument();
    expect(screen.getByTestId('chart-stage')).toBeInTheDocument();
    expect(screen.getByTestId('table-section')).toBeInTheDocument();
    expect(screen.getByText('ORD-001')).toBeInTheDocument();
    expect(screen.getByText('ORD-002')).toBeInTheDocument();
  });

  it('toggles fullscreen layout mode on click', async () => {
    render(<InteractiveDashboardArtifact content={sampleJsonContent} />);

    const root = screen.getByTestId('interactive-dashboard-artifact-root');
    expect(root.className).not.toContain('fixed inset-0');

    const fullscreenBtn = screen.getByTestId('fullscreen-toggle-btn');
    await act(async () => {
      fireEvent.click(fullscreenBtn);
    });

    expect(root.className).toContain('fixed inset-0');

    // Toggle back
    await act(async () => {
      fireEvent.click(fullscreenBtn);
    });
    expect(root.className).not.toContain('fixed inset-0');
  });

  it('switches chart mode between bar and line', async () => {
    render(<InteractiveDashboardArtifact content={sampleJsonContent} />);

    const lineBtn = screen.getByTestId('chart-mode-line-btn');
    await act(async () => {
      fireEvent.click(lineBtn);
    });

    const svg = screen.getByTestId('chart-svg-container');
    expect(svg.querySelector('polyline')).not.toBeNull();

    const barBtn = screen.getByTestId('chart-mode-bar-btn');
    await act(async () => {
      fireEvent.click(barBtn);
    });

    expect(svg.querySelector('polyline')).toBeNull();
  });

  it('filters table rows based on search input', async () => {
    render(<InteractiveDashboardArtifact content={sampleJsonContent} />);

    const searchInput = screen.getByTestId('table-search-input');
    expect(screen.getByText('ORD-001')).toBeInTheDocument();
    expect(screen.getByText('ORD-002')).toBeInTheDocument();
    expect(screen.getByText('ORD-003')).toBeInTheDocument();

    // Type "北美"
    await act(async () => {
      fireEvent.change(searchInput, { target: { value: '北美' } });
    });

    expect(screen.getByText('ORD-001')).toBeInTheDocument();
    expect(screen.queryByText('ORD-002')).toBeNull();
    expect(screen.queryByText('ORD-003')).toBeNull();

    // Clear search
    await act(async () => {
      fireEvent.change(searchInput, { target: { value: '' } });
    });

    expect(screen.getByText('ORD-001')).toBeInTheDocument();
    expect(screen.getByText('ORD-002')).toBeInTheDocument();
    expect(screen.getByText('ORD-003')).toBeInTheDocument();
  });

  it('copies metric summary to clipboard', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(<InteractiveDashboardArtifact content={sampleJsonContent} />);

    const copyBtn = screen.getByTestId('copy-dashboard-btn');
    await act(async () => {
      fireEvent.click(copyBtn);
    });

    expect(writeTextMock).toHaveBeenCalledTimes(1);
    expect(writeTextMock.mock.calls[0][0]).toContain('全球电商运营监控大盘');
    expect(writeTextMock.mock.calls[0][0]).toContain('GMV');
  });

  it('downloads standalone HTML when export button is clicked', async () => {
    const onDownloadMock = vi.fn();
    const createObjectURLMock = vi.fn().mockReturnValue('blob:dummy-html');
    const revokeObjectURLMock = vi.fn();
    window.URL.createObjectURL = createObjectURLMock;
    window.URL.revokeObjectURL = revokeObjectURLMock;

    render(
      <InteractiveDashboardArtifact
        content={sampleJsonContent}
        onDownloadHtml={onDownloadMock}
      />
    );

    const downloadBtn = screen.getByTestId('download-html-btn');
    await act(async () => {
      fireEvent.click(downloadBtn);
    });

    expect(createObjectURLMock).toHaveBeenCalledTimes(1);
    expect(revokeObjectURLMock).toHaveBeenCalledTimes(1);
    expect(onDownloadMock).toHaveBeenCalledTimes(1);
  });
});
