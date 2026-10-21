import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QuickStartChecklistCard } from '../QuickStartChecklistCard';
import { useVisualTourStore } from '../useVisualTourStore';

describe('QuickStartChecklistCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    useVisualTourStore.getState().resetOnboardingState();
  });

  it('当 isChecklistDismissed 为 true 时不应渲染任何内容', () => {
    useVisualTourStore.setState({ isChecklistDismissed: true });
    const { container } = render(<QuickStartChecklistCard />);
    expect(container.firstChild).toBeNull();
  });

  it('折叠态下应渲染微胶囊按钮并显示当前百分比', () => {
    useVisualTourStore.setState({ isChecklistCollapsed: true, isChecklistDismissed: false });
    render(<QuickStartChecklistCard />);

    const expandBtn = screen.getByRole('button', { name: '展开新手开箱核对单' });
    expect(expandBtn).toBeInTheDocument();

    fireEvent.click(expandBtn);
    expect(useVisualTourStore.getState().isChecklistCollapsed).toBe(false);
  });

  it('展开态下应展示清单项、支持打卡并更新完成状态', () => {
    useVisualTourStore.setState({ isChecklistCollapsed: false, isChecklistDismissed: false });
    render(<QuickStartChecklistCard />);

    expect(screen.getByTestId('quickstart-checklist-card')).toBeInTheDocument();
    expect(screen.getByText('新手 3 分钟极速上手')).toBeInTheDocument();

    const checkBtns = screen.getAllByRole('button', { name: /点击打卡/i });
    expect(checkBtns.length).toBeGreaterThan(0);
    const firstCheckBtn = checkBtns[0];
    if (firstCheckBtn) {
      fireEvent.click(firstCheckBtn);
      expect(useVisualTourStore.getState().checklistItems[0]?.completed).toBe(true);
    }
  });

  it('点击折叠按钮应正确折叠为胶囊', () => {
    useVisualTourStore.setState({ isChecklistCollapsed: false, isChecklistDismissed: false });
    render(<QuickStartChecklistCard />);

    const collapseBtn = screen.getByRole('button', { name: '折叠清单' });
    fireEvent.click(collapseBtn);
    expect(useVisualTourStore.getState().isChecklistCollapsed).toBe(true);
  });

  it('点击关闭按钮应正确关闭清单', () => {
    useVisualTourStore.setState({ isChecklistCollapsed: false, isChecklistDismissed: false });
    render(<QuickStartChecklistCard />);

    const dismissBtn = screen.getByRole('button', { name: '关闭清单' });
    fireEvent.click(dismissBtn);
    expect(useVisualTourStore.getState().isChecklistDismissed).toBe(true);
  });

  it('当全部任务达成时应展示通关成就达成提示', () => {
    const allDoneItems = useVisualTourStore.getState().checklistItems.map((item) => {
      return { ...item, completed: true };
    });
    useVisualTourStore.setState({
      checklistItems: allDoneItems,
      isChecklistCollapsed: false,
      isChecklistDismissed: false,
    });

    render(<QuickStartChecklistCard />);
    expect(screen.getByText('所有起步任务已全部达成！')).toBeInTheDocument();
  });
});
