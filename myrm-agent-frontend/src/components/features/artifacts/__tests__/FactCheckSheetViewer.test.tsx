import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FactCheckSheetViewer } from '../FactCheckSheetViewer';
import type { FactCheckSheet } from '../deliverableTypes';

const mockTranslations: Record<string, string> = {
  title: '多源事实核查与冲突仲裁表',
  summaryTitle: '质检总览与冲突仲裁',
  totalItems: '核查总项',
  criticalConflicts: '严重冲突',
  warnings: '差异演进',
  infoDifferences: '描述差异',
  unresolvedItems: '待确认争议',
  searchPlaceholder: '搜索事实主题、采纳口径或文档...',
  filterAll: '全部严重度',
  filterCritical: '仅看严重冲突',
  filterWarning: '仅看差异演进',
  filterInfo: '仅看描述差异',
  adoptedStandard: '采纳标准口径',
  rationale: '裁定依据',
  confidence: '置信度',
  multiSourceMatrix: '多源素材对照矩阵',
  sourceDoc: '来源文档',
  claimedValue: '主张数据',
  anchorTimestamp: '锚点 / 时效',
  contextSnippet: '上下文摘录',
  affectedDeliverables: '已同步修正的交付物',
  statusResolved: '已采纳最新权威口径',
  statusUnresolved: '待人工最终确认',
  statusConditional: '条件分支生效',
  noItemsFound: '未检索到匹配的事实核查项',
  loading: '正在加载事实核查表...',
  close: '关闭',
};

const stableT = (key: string) => mockTranslations[key] || key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/api', () => ({
  getApiUrl: () => 'http://127.0.0.1:8080',
}));

const mockSheet: FactCheckSheet = {
  sheet_id: 'sheet_alpha_123',
  session_id: 'sess_test',
  title: '发布会多源事实核查与口径仲裁清单',
  summary: '对官方零售价、首发优惠及交付时间进行了多源互证与仲裁',
  created_at: 1725364800,
  items: [
    {
      id: 'fci_001',
      claim_topic: '官方首发零售价',
      severity: 'critical',
      status: 'resolved',
      sources: [
        {
          source_uri: 'vault://meeting_minutes.docx',
          document_title: '内测发布会纪要.docx',
          line_anchor: 'L42-L45',
          claimed_value: '1699元',
          snippet: '首批受邀客户可享受内测价 1699 元。',
          timestamp_hint: '2026-07-15',
        },
        {
          source_uri: 'vault://official_announcement.pdf',
          document_title: '正式发布会定价通告.pdf',
          line_anchor: 'P3',
          claimed_value: '1999元',
          snippet: '官方首发零售价 1999 元，首发特惠 1799 元。',
          timestamp_hint: '2026-08-20',
        },
      ],
      adopted_value: '1999元 (首发特惠1799元)',
      resolution_rationale: '8月20日高管定稿晚于7月内测纪要，以最终上市通告为准',
      confidence_score: 0.98,
      affected_artifacts: ['01_articles/launch.md', '02_social_post/weibo.png'],
    },
    {
      id: 'fci_002',
      claim_topic: '首批全量发货日期',
      severity: 'warning',
      status: 'resolved',
      sources: [
        {
          source_uri: 'vault://memo.pdf',
          document_title: '供应链排产备忘.pdf',
          claimed_value: '2026-09-15',
          snippet: '工厂预计9月15日完成首批入库',
        },
      ],
      adopted_value: '2026-09-20',
      resolution_rationale: '考虑质检与物流周转顺延5天',
      confidence_score: 0.92,
      affected_artifacts: ['04_data_sheets/schedule.xlsx'],
    },
    {
      id: 'fci_003',
      claim_topic: '外壳材质工艺描述',
      severity: 'info',
      status: 'conditional',
      sources: [
        {
          source_uri: 'vault://spec.md',
          document_title: '工业设计规格.md',
          claimed_value: '阳极氧化铝合金',
        },
      ],
      adopted_value: '航空级阳极氧化铝合金',
      resolution_rationale: '对外宣传用统一物料词',
      confidence_score: 0.95,
    },
  ],
};

describe('FactCheckSheetViewer', () => {
  it('renders correctly when open with sheet data', () => {
    render(<FactCheckSheetViewer open={true} onOpenChange={vi.fn()} sheet={mockSheet} />);

    expect(screen.getByText('发布会多源事实核查与口径仲裁清单')).toBeInTheDocument();
    expect(screen.getByText('对官方零售价、首发优惠及交付时间进行了多源互证与仲裁')).toBeInTheDocument();

    // 统计指标
    expect(screen.getByText(/核查总项/)).toBeInTheDocument();
    expect(screen.getAllByText(/严重冲突/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/差异演进/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/描述差异/).length).toBeGreaterThan(0);

    // 核查条目
    expect(screen.getByText('官方首发零售价')).toBeInTheDocument();
    expect(screen.getByText('首批全量发货日期')).toBeInTheDocument();
    expect(screen.getByText('外壳材质工艺描述')).toBeInTheDocument();
  });

  it('filters items by severity', () => {
    render(<FactCheckSheetViewer open={true} onOpenChange={vi.fn()} sheet={mockSheet} />);

    // 点击“仅看严重冲突”
    const criticalFilterBtn = screen.getByText(/仅看严重冲突/);
    fireEvent.click(criticalFilterBtn);

    expect(screen.getByText('官方首发零售价')).toBeInTheDocument();
    expect(screen.queryByText('首批全量发货日期')).not.toBeInTheDocument();
    expect(screen.queryByText('外壳材质工艺描述')).not.toBeInTheDocument();
  });

  it('searches and filters items by keyword', () => {
    render(<FactCheckSheetViewer open={true} onOpenChange={vi.fn()} sheet={mockSheet} />);

    const searchInput = screen.getByPlaceholderText('搜索事实主题、采纳口径或文档...');
    fireEvent.change(searchInput, { target: { value: '铝合金' } });

    expect(screen.getByText('外壳材质工艺描述')).toBeInTheDocument();
    expect(screen.queryByText('官方首发零售价')).not.toBeInTheDocument();
    expect(screen.queryByText('首批全量发货日期')).not.toBeInTheDocument();
  });

  it('displays multi-source claim details and affected deliverables', () => {
    render(<FactCheckSheetViewer open={true} onOpenChange={vi.fn()} sheet={mockSheet} />);

    expect(screen.getByText('内测发布会纪要.docx')).toBeInTheDocument();
    expect(screen.getByText('正式发布会定价通告.pdf')).toBeInTheDocument();
    expect(screen.getByText('1699元')).toBeInTheDocument();
    expect(screen.getByText('1999元')).toBeInTheDocument();
    expect(screen.getByText('01_articles/launch.md')).toBeInTheDocument();
    expect(screen.getByText('02_social_post/weibo.png')).toBeInTheDocument();
  });

  it('handles empty items and displays fallback correctly', () => {
    const emptySheet: FactCheckSheet = {
      sheet_id: 'sheet_empty',
      title: '空核查表',
      created_at: 1725364800,
      items: [],
    };
    render(<FactCheckSheetViewer open={true} onOpenChange={vi.fn()} sheet={emptySheet} />);
    expect(screen.getByText('空核查表')).toBeInTheDocument();
    expect(screen.getByText('未检索到匹配的事实核查项')).toBeInTheDocument();
  });

  it('fetches sheet from vaultUri when sheet prop is not passed', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockSheet,
    } as Response);

    render(<FactCheckSheetViewer open={true} onOpenChange={vi.fn()} vaultUri="vault://test-uuid-fact-123" />);

    expect(fetchSpy).toHaveBeenCalledWith('http://127.0.0.1:8080/api/v1/files/vault/test-uuid-fact-123');
    fetchSpy.mockRestore();
  });
});
