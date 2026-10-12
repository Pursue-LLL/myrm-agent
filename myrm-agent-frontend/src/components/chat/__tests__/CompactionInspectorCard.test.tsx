import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import {
  CompactionInspectorCard,
  CompactionInspectorCardData,
} from '../CompactionInspectorCard';

describe('CompactionInspectorCard', () => {
  const sampleData: CompactionInspectorCardData = {
    cardId: 'card-1',
    chatId: 'chat-abc',
    preTokens: 10000,
    postTokens: 2500,
    savedTokens: 7500,
    savingsRatio: 0.75,
    compactedTurnsCount: 6,
    preservedPinnedCount: 2,
    structuredSummaryText: '重构了用户支付回调路由，移除了冗余的死代码。',
    keyDecisions: ['采用指数退避重试', '关键配置持久化在安全金库中'],
    pinnedItemsPreview: ['📌 规则 1: 绝对禁止使用 Any 类型', '📌 核心契约: UUIDv7 主键'],
    isUserEditable: true,
  };

  it('renders collapsed card metrics correctly', () => {
    render(<CompactionInspectorCard data={sampleData} />);

    expect(screen.getByTestId('compaction-inspector-card')).toBeInTheDocument();
    expect(screen.getByText('上下文透明压缩完成')).toBeInTheDocument();
    expect(screen.getByText('节省 75%')).toBeInTheDocument();
    expect(screen.getByText('10,000 → 2,500 tokens')).toBeInTheDocument();
    expect(screen.getByText('7,500')).toBeInTheDocument();
    expect(screen.getByText('6')).toBeInTheDocument();
    expect(screen.getByText('2 项')).toBeInTheDocument();
    expect(screen.queryByTestId('expanded-details')).not.toBeInTheDocument();
  });

  it('toggles expansion to reveal structured summary, decisions, and pinned items', () => {
    render(<CompactionInspectorCard data={sampleData} />);

    const toggleBtn = screen.getByTestId('toggle-expand-btn');
    expect(toggleBtn).toHaveTextContent('查看详情 ▼');

    fireEvent.click(toggleBtn);
    expect(toggleBtn).toHaveTextContent('收起详情 ▲');
    expect(screen.getByTestId('expanded-details')).toBeInTheDocument();

    expect(screen.getByText('重构了用户支付回调路由，移除了冗余的死代码。')).toBeInTheDocument();
    expect(screen.getByText('采用指数退避重试')).toBeInTheDocument();
    expect(screen.getByText('📌 规则 1: 绝对禁止使用 Any 类型')).toBeInTheDocument();

    fireEvent.click(toggleBtn);
    expect(screen.queryByTestId('expanded-details')).not.toBeInTheDocument();
  });

  it('allows inline editing of structured summary and calls onSaveSummary', () => {
    const handleSave = vi.fn();
    render(<CompactionInspectorCard data={sampleData} onSaveSummary={handleSave} />);

    fireEvent.click(screen.getByTestId('toggle-expand-btn'));
    fireEvent.click(screen.getByTestId('edit-summary-btn'));

    const textarea = screen.getByTestId('summary-textarea');
    expect(textarea).toHaveValue('重构了用户支付回调路由，移除了冗余的死代码。');

    fireEvent.change(textarea, { target: { value: '人工微调后的结构化会话摘要。' } });
    fireEvent.click(screen.getByTestId('save-summary-btn'));

    expect(handleSave).toHaveBeenCalledWith('人工微调后的结构化会话摘要。');
    expect(screen.getByText('人工微调后的结构化会话摘要。')).toBeInTheDocument();
  });
});
