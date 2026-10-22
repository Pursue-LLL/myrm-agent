import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { InSituWorkflowSkillPickerDrawer } from '../InSituWorkflowSkillPickerDrawer';
import { useInSituSkillPickerStore } from '../useInSituSkillPickerStore';

describe('InSituWorkflowSkillPickerDrawer', () => {
  beforeEach(() => {
    useInSituSkillPickerStore.getState().resetToDefault();
    vi.restoreAllMocks();
  });

  it('初始状态渲染折叠态的唤出顶条，点击后展开抽屉与 NoiseGauge 看板', () => {
    render(<InSituWorkflowSkillPickerDrawer />);

    expect(
      screen.getByTestId('in-situ-skill-picker-drawer-container')
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('in-situ-skill-drawer-body')
    ).not.toBeInTheDocument();

    const toggleBtn = screen.getByTestId('toggle-drawer-btn');
    fireEvent.click(toggleBtn);

    expect(screen.getByTestId('in-situ-skill-drawer-body')).toBeInTheDocument();
    expect(screen.getByTestId('noise-gauge-panel')).toBeInTheDocument();
    expect(screen.getByTestId('noise-level-badge')).toHaveTextContent(
      /动作空间:/
    );
  });

  it('展开抽屉后正确渲染技能卡片并支持一键挂载', () => {
    useInSituSkillPickerStore.getState().setIsDrawerOpen(true);
    render(<InSituWorkflowSkillPickerDrawer />);

    expect(
      screen.getByTestId('in-situ-skill-card-skill-excel-analytics')
    ).toBeInTheDocument();

    const mountBtn = screen.getByTestId(
      'mount-toggle-btn-skill-excel-analytics'
    );
    expect(mountBtn).toHaveTextContent('+ 挂载');

    fireEvent.click(mountBtn);

    expect(mountBtn).toHaveTextContent('已挂载');
    const skill = useInSituSkillPickerStore
      .getState()
      .skills.find((s) => s.id === 'skill-excel-analytics');
    expect(skill?.isMounted).toBe(true);
  });

  it('搜索输入框输入关键词能够即时过滤卡片', () => {
    useInSituSkillPickerStore.getState().setIsDrawerOpen(true);
    render(<InSituWorkflowSkillPickerDrawer />);

    const searchInput = screen.getByPlaceholderText(/搜索技能名称/);
    fireEvent.change(searchInput, { target: { value: 'PDF' } });

    expect(
      screen.getByTestId('in-situ-skill-card-skill-pdf-extractor')
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('in-situ-skill-card-skill-excel-analytics')
    ).not.toBeInTheDocument();
  });

  it('分类标签切换能够按领域筛选技能', () => {
    useInSituSkillPickerStore.getState().setIsDrawerOpen(true);
    render(<InSituWorkflowSkillPickerDrawer />);

    const filterBtn = screen.getByTestId('category-filter-网页检索');
    fireEvent.click(filterBtn);

    expect(
      screen.getByTestId('in-situ-skill-card-skill-web-scraper-pro')
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('in-situ-skill-card-skill-excel-analytics')
    ).not.toBeInTheDocument();
  });

  it('鼠标悬停在未挂载技能上时在 NoiseGauge 中显示增量预估', () => {
    useInSituSkillPickerStore.getState().setIsDrawerOpen(true);
    render(<InSituWorkflowSkillPickerDrawer />);

    const unmountedCard = screen.getByTestId(
      'in-situ-skill-card-skill-excel-analytics'
    );
    fireEvent.mouseEnter(unmountedCard);

    expect(screen.getByTestId('noise-preview-delta')).toBeInTheDocument();
    expect(screen.getByTestId('noise-preview-delta')).toHaveTextContent(
      /若挂载将增加: \+520 tok/
    );

    fireEvent.mouseLeave(unmountedCard);
    expect(screen.queryByTestId('noise-preview-delta')).not.toBeInTheDocument();
  });
});
