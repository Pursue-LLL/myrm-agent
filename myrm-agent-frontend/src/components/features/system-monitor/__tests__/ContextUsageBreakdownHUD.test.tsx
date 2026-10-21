import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ContextUsageBreakdownHUD } from '../ContextUsageBreakdownHUD';
import type { ContextBreakdownData } from '../contextBreakdownTypes';

describe('ContextUsageBreakdownHUD', () => {
  const mockData: ContextBreakdownData = {
    total_window_tokens: 128000,
    provider_actual_tokens: 83200,
    estimated_sum_tokens: 82000,
    usage_ratio_pct: 65.0,
    alert_level: 'WARNING_60',
    alert_message: '已跨越 60% 性能临界点，模型开始出现注意力衰减，建议压缩上下文。',
    categories: {
      system_prompt: {
        category: 'system_prompt',
        label_zh: '系统设定 (System)',
        estimated_tokens: 4200,
        percentage: 5.1,
        color_hex: '#38bdf8',
      },
      memory: {
        category: 'memory',
        label_zh: '长期记忆 (Memory)',
        estimated_tokens: 12000,
        percentage: 14.4,
        color_hex: '#a855f7',
      },
      workspace: {
        category: 'workspace',
        label_zh: '工作区规则 (Rules)',
        estimated_tokens: 8500,
        percentage: 10.2,
        color_hex: '#3b82f6',
      },
      skills: {
        category: 'skills',
        label_zh: '技能目录 (Skills)',
        estimated_tokens: 6500,
        percentage: 7.8,
        color_hex: '#10b981',
      },
      tools_schema: {
        category: 'tools_schema',
        label_zh: '工具定义 (Tools Schema)',
        estimated_tokens: 15000,
        percentage: 18.0,
        color_hex: '#06b6d4',
      },
      tool_results: {
        category: 'tool_results',
        label_zh: '工具返回 (Tool Output)',
        estimated_tokens: 22000,
        percentage: 26.4,
        color_hex: '#f59e0b',
      },
      chat_messages: {
        category: 'chat_messages',
        label_zh: '对话历史 (Chat)',
        estimated_tokens: 13800,
        percentage: 16.6,
        color_hex: '#64748b',
      },
    },
  };

  it('renders context breakdown HUD with alert badge, 60%/90% markers, dual metrics, and seven categories', () => {
    const onRefresh = vi.fn();
    const onTriggerCompact = vi.fn();

    render(
      <ContextUsageBreakdownHUD
        data={mockData}
        onRefresh={onRefresh}
        onTriggerCompact={onTriggerCompact}
      />
    );

    // 标题与 WARNING_60 徽章
    expect(
      screen.getByText('上下文用量七分类透视与警戒线 HUD (WorkBuddy Breakdown)')
    ).toBeInTheDocument();
    expect(
      screen.getByText('跨越 60% 性能临界点 (Degradation Warning)')
    ).toBeInTheDocument();

    // 标尺警戒线
    expect(screen.getByText('▲ 60% 警戒线')).toBeInTheDocument();
    expect(screen.getByText('▲ 90% 熔断线')).toBeInTheDocument();
    expect(screen.getByText('65% 窗口占用')).toBeInTheDocument();

    // 双口径展示：估算总和 82,000 vs 提供商实报 83,200
    expect(screen.getByText('82,000')).toBeInTheDocument();
    expect(screen.getAllByText('83,200').length).toBeGreaterThanOrEqual(2);

    // 七分类卡片标签与数值渲染
    expect(screen.getByText('系统设定 (System)')).toBeInTheDocument();
    expect(screen.getByText('长期记忆 (Memory)')).toBeInTheDocument();
    expect(screen.getByText('工作区规则 (Rules)')).toBeInTheDocument();
    expect(screen.getByText('技能目录 (Skills)')).toBeInTheDocument();
    expect(screen.getByText('工具定义 (Tools Schema)')).toBeInTheDocument();
    expect(screen.getByText('工具返回 (Tool Output)')).toBeInTheDocument();
    expect(screen.getByText('对话历史 (Chat)')).toBeInTheDocument();

    expect(screen.getByText('22,000')).toBeInTheDocument();
    expect(screen.getByText('26.4%')).toBeInTheDocument();

    // 交互按钮
    const refreshBtn = screen.getByText('刷新用量');
    fireEvent.click(refreshBtn);
    expect(onRefresh).toHaveBeenCalledTimes(1);

    const compactBtn = screen.getByText('一键压缩上下文');
    fireEvent.click(compactBtn);
    expect(onTriggerCompact).toHaveBeenCalledTimes(1);
  });
});
