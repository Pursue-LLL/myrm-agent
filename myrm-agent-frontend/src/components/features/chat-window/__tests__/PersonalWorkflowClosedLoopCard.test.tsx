import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { PersonalWorkflowClosedLoopCard } from '../PersonalWorkflowClosedLoopCard';
import useChatStore from '@/store/useChatStore';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => {
    const translations: Record<string, string> = {
      badge: '三位一体闭环',
      title: '个人工作流闭环：待办 · 日志 · 周报',
      desc: '以看板待办为输入源，沉淀每日日志事实，自动聚合生成高质量结构化周报。',
      step1Title: '待办拆解',
      step1Desc: 'Kanban 看板任务梳理与阶段跟踪',
      step1Prompt: '帮我梳理并拆解当前的核心工作待办事项。',
      step2Title: '日常对账',
      step2Desc: 'DailyJournal 记录事实与决策卡点',
      step2Prompt: '帮我记录并整理今日工作日志。',
      step3Title: '智能周报',
      step3Desc: 'WeeklyReview 蓝图聚合度量产出',
      step3Prompt: '帮我聚合生成一份标准本周工作总结报告。',
      oneClickAction: '一键加载闭环 Prompt',
    };
    return translations[key] || key;
  },
}));

describe('PersonalWorkflowClosedLoopCard', () => {
  beforeEach(() => {
    useChatStore.setState({ inputMessage: '' });
  });

  it('renders all three steps correctly with titles and badges', () => {
    render(<PersonalWorkflowClosedLoopCard />);

    expect(screen.getByText('三位一体闭环')).toBeDefined();
    expect(screen.getByText('个人工作流闭环：待办 · 日志 · 周报')).toBeDefined();
    expect(screen.getByText('待办拆解')).toBeDefined();
    expect(screen.getByText('日常对账')).toBeDefined();
    expect(screen.getByText('智能周报')).toBeDefined();
  });

  it('clicking a step injects corresponding prompt into chatStore', () => {
    render(<PersonalWorkflowClosedLoopCard />);

    const step3Button = screen.getByText('智能周报').closest('button');
    expect(step3Button).not.toBeNull();

    fireEvent.click(step3Button!);

    expect(useChatStore.getState().inputMessage).toBe('帮我聚合生成一份标准本周工作总结报告。');
  });
});
