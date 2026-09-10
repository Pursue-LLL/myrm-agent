import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import PersonalTodoClosedLoopCard from '../PersonalTodoClosedLoopCard';
import useChatStore from '@/store/useChatStore';

const stableT = (key: string) => {
  const translations: Record<string, string> = {
    badge: '三位一体闭环',
    title: '个人工作流闭环：待办 · 日志 · 周报',
    desc: '以看板待办为输入源，沉淀每日日志事实，自动聚合生成高质量结构化周报。',
    step1Title: '待办拆解',
    step1Desc: 'Kanban 看板任务梳理',
    step1Prompt: '帮我梳理并拆解当前的核心工作待办事项。',
    step2Title: '日常对账',
    step2Desc: 'DailyJournal 记录事实',
    step2Prompt: '帮我记录并整理今日工作日志。',
    step3Title: '智能周报',
    step3Desc: 'WeeklyReview 蓝图聚合',
    step3Prompt: '帮我调取本周完成的待办事项与每日日志生成周报。',
  };
  return translations[key] || key;
};

// Mock next-intl
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('PersonalTodoClosedLoopCard', () => {
  beforeEach(() => {
    useChatStore.setState({ inputMessage: '' });
  });

  it('renders all three steps correctly', () => {
    render(<PersonalTodoClosedLoopCard />);

    expect(screen.getByText('三位一体闭环')).toBeDefined();
    expect(screen.getByText('个人工作流闭环：待办 · 日志 · 周报')).toBeDefined();
    expect(screen.getByText('待办拆解')).toBeDefined();
    expect(screen.getByText('日常对账')).toBeDefined();
    expect(screen.getByText('智能周报')).toBeDefined();
  });

  it('sets input message when a step card is clicked', () => {
    render(<PersonalTodoClosedLoopCard />);

    const step1Btn = screen.getByText('待办拆解').closest('button');
    expect(step1Btn).toBeDefined();

    fireEvent.click(step1Btn!);
    expect(useChatStore.getState().inputMessage).toBe('帮我梳理并拆解当前的核心工作待办事项。');

    const step3Btn = screen.getByText('智能周报').closest('button');
    fireEvent.click(step3Btn!);
    expect(useChatStore.getState().inputMessage).toBe('帮我调取本周完成的待办事项与每日日志生成周报。');
  });
});
