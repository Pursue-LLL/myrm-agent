import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { HighYieldRoutineCatalog } from '../HighYieldRoutineCatalog';
import type { HighYieldRoutineSpec } from '../roiTypes';

const mockTranslations = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => mockTranslations,
}));

describe('HighYieldRoutineCatalog', () => {
  const dummyRoutines: HighYieldRoutineSpec[] = [
    {
      routine_id: 'routine_market_radar',
      title_zh: '行业竞品每日动态雷达',
      title_en: 'Daily Competitor Tech Radar',
      description_zh: '自动抓取 GitHub 趋势榜与技术博客，提炼 3 篇重点竞品动态与架构差异',
      description_en: 'Scrape GitHub trending and blogs',
      estimated_minutes_saved: 120,
      typical_roi_multiplier: 185.0,
      category: 'market_research',
      preset_prompt: '调研最近 24 小时 AI Agent 领域的热门开源项目演进',
    },
    {
      routine_id: 'routine_chat_digest',
      title_zh: '未读群聊重点萃取与待办提取',
      title_en: 'Unread Chat Action Items Extractor',
      description_zh: '聚合长篇技术讨论群记录，自动滤除闲聊并萃取 Action Items',
      description_en: 'Summarize lengthy chat discussions',
      estimated_minutes_saved: 45,
      typical_roi_multiplier: 120.0,
      category: 'chat_digest',
      preset_prompt: '分析群聊记录中的核心决策点与未决议题',
    },
  ];

  it('renders all routine cards with ROI badge and time saved indicator', () => {
    render(<HighYieldRoutineCatalog routines={dummyRoutines} />);

    expect(screen.getByTestId('high-yield-routine-catalog-root')).toBeInTheDocument();
    expect(screen.getByTestId('routine-card-routine_market_radar')).toBeInTheDocument();
    expect(screen.getByTestId('routine-card-routine_chat_digest')).toBeInTheDocument();

    expect(screen.getByText('行业竞品每日动态雷达')).toBeInTheDocument();
    expect(screen.getByText('185x ROI')).toBeInTheDocument();
    expect(screen.getByText('~120m')).toBeInTheDocument();

    expect(screen.getByText('未读群聊重点萃取与待办提取')).toBeInTheDocument();
    expect(screen.getByText('120x ROI')).toBeInTheDocument();
    expect(screen.getByText('~45m')).toBeInTheDocument();
  });

  it('calls onTriggerRoutine when trigger button is clicked', () => {
    const onTriggerMock = vi.fn();
    render(
      <HighYieldRoutineCatalog
        routines={dummyRoutines}
        onTriggerRoutine={onTriggerMock}
      />
    );

    const triggerBtn = screen.getByTestId('trigger-routine-btn-routine_market_radar');
    fireEvent.click(triggerBtn);

    expect(onTriggerMock).toHaveBeenCalledTimes(1);
    expect(onTriggerMock).toHaveBeenCalledWith(
      expect.objectContaining({
        routine_id: 'routine_market_radar',
        category: 'market_research',
      })
    );
  });
});
