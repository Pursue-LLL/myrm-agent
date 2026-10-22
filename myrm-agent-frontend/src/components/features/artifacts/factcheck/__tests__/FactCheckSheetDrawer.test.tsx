/** @vitest-environment jsdom */

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FactCheckSheetDrawer } from '../FactCheckSheetDrawer';
import { PlaceholderItem, VerifiedFactItem } from '../factCheckTypes';

const stableT = (key: string, values?: Record<string, string | number>) => {
  const table: Record<string, string> = {
    drawerTitle: '事实核查与占位管理',
    drawerSubtitle: '不编造数据，把即兴演练的虚构骨架与已核实事实严密管起来',
    tabPlaceholders: '待替换占位',
    tabVerified: '已核实硬事实',
    placeholderTag: '待实测',
    applied: '已替换',
    contextLabel: '上下文摘录',
    inputRealValuePlaceholder: '输入真实跑测数据...',
    applyBtn: '替换',
    replaceAllBtn: '一键全部替换并定稿',
    verifiedTag: '已核实',
    close: '关闭',
  };
  if (key === 'bannerWarning' && values?.count !== undefined) {
    return `本篇草案包含 ${values.count} 处待实测占位数据`;
  }
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('FactCheckSheetDrawer', () => {
  const mockPlaceholders: PlaceholderItem[] = [
    {
      id: 'ph-1',
      originalText: '[待替换占位: 3分42秒]',
      placeholderKey: '3分42秒',
      contextSnippet: '...平均处理耗时为 [待替换占位: 3分42秒]，性能显著...',
      status: 'pending',
      index: 10,
    },
    {
      id: 'ph-2',
      originalText: '{{placeholder:99.2%}}',
      placeholderKey: '99.2%',
      contextSnippet: '...通过率达到 {{placeholder:99.2%}} 符合标准...',
      status: 'pending',
      index: 50,
    },
  ];

  const mockVerifiedFacts: VerifiedFactItem[] = [
    {
      id: 'vf-1',
      factStatement: 'API 官方调用单价为 0.14 美元/百万 Token',
      verifiedValue: '$0.14 / 1M',
      sourceName: '官方定价文档',
      sourceUrl: 'https://example.com/pricing',
      verifiedAt: '2026-09-02',
    },
  ];

  it('does not render when isOpen is false', () => {
    const { container } = render(
      <FactCheckSheetDrawer
        isOpen={false}
        onClose={vi.fn()}
        placeholders={mockPlaceholders}
        verifiedFacts={mockVerifiedFacts}
        onReplacePlaceholder={vi.fn()}
        onReplaceAllAndFinalize={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders drawer with tabs and pending placeholders when isOpen is true', () => {
    render(
      <FactCheckSheetDrawer
        isOpen={true}
        onClose={vi.fn()}
        placeholders={mockPlaceholders}
        verifiedFacts={mockVerifiedFacts}
        onReplacePlaceholder={vi.fn()}
        onReplaceAllAndFinalize={vi.fn()}
      />,
    );

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('事实核查与占位管理')).toBeInTheDocument();
    expect(screen.getByText('待替换占位')).toBeInTheDocument();
    expect(screen.getByText('[待替换占位: 3分42秒]')).toBeInTheDocument();
    expect(screen.getByText('{{placeholder:99.2%}}')).toBeInTheDocument();
  });

  it('allows typing real value and applying single replacement', () => {
    const handleReplace = vi.fn();

    render(
      <FactCheckSheetDrawer
        isOpen={true}
        onClose={vi.fn()}
        placeholders={mockPlaceholders}
        verifiedFacts={mockVerifiedFacts}
        onReplacePlaceholder={handleReplace}
        onReplaceAllAndFinalize={vi.fn()}
      />,
    );

    const input = screen.getByLabelText('Real value for 3分42秒');
    fireEvent.change(input, { target: { value: '2分05秒' } });

    const applyButtons = screen.getAllByRole('button', { name: '替换' });
    fireEvent.click(applyButtons[0]);

    expect(handleReplace).toHaveBeenCalledWith('ph-1', '2分05秒');
  });

  it('supports replace all and finalize button', () => {
    const handleReplaceAll = vi.fn();

    render(
      <FactCheckSheetDrawer
        isOpen={true}
        onClose={vi.fn()}
        placeholders={mockPlaceholders}
        verifiedFacts={mockVerifiedFacts}
        onReplacePlaceholder={vi.fn()}
        onReplaceAllAndFinalize={handleReplaceAll}
      />,
    );

    const input1 = screen.getByLabelText('Real value for 3分42秒');
    fireEvent.change(input1, { target: { value: '2分05秒' } });

    const replaceAllBtn = screen.getByRole('button', { name: /一键全部替换并定稿/i });
    fireEvent.click(replaceAllBtn);

    expect(handleReplaceAll).toHaveBeenCalledWith({
      'ph-1': '2分05秒',
    });
  });

  it('allows switching to verified facts tab and shows citations', () => {
    render(
      <FactCheckSheetDrawer
        isOpen={true}
        onClose={vi.fn()}
        placeholders={mockPlaceholders}
        verifiedFacts={mockVerifiedFacts}
        onReplacePlaceholder={vi.fn()}
        onReplaceAllAndFinalize={vi.fn()}
      />,
    );

    const verifiedTab = screen.getByRole('button', { name: /已核实硬事实/i });
    fireEvent.click(verifiedTab);

    expect(screen.getByText('API 官方调用单价为 0.14 美元/百万 Token')).toBeInTheDocument();
    expect(screen.getByText('官方定价文档')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /官方定价文档/i });
    expect(link).toHaveAttribute('href', 'https://example.com/pricing');
  });

  it('calls onClose when close button is clicked', () => {
    const handleClose = vi.fn();

    render(
      <FactCheckSheetDrawer
        isOpen={true}
        onClose={handleClose}
        placeholders={mockPlaceholders}
        verifiedFacts={mockVerifiedFacts}
        onReplacePlaceholder={vi.fn()}
        onReplaceAllAndFinalize={vi.fn()}
      />,
    );

    const closeBtn = screen.getByRole('button', { name: '关闭' });
    fireEvent.click(closeBtn);

    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
