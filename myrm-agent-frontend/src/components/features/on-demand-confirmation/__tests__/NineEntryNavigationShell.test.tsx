import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { NineEntryNavigationShell } from '../NineEntryNavigationShell';
import { useOnDemandConfirmationStore } from '../useOnDemandConfirmationStore';

describe('NineEntryNavigationShell 组件单测', () => {
  beforeEach(() => {
    useOnDemandConfirmationStore.setState({
      activeNavEntryId: 'main_chat',
    });
  });

  it('完整渲染九大入口中枢容器、分类标题与各导航项目', () => {
    render(<NineEntryNavigationShell />);

    expect(screen.getByTestId('nine-entry-nav-shell')).toBeInTheDocument();
    expect(screen.getByText('工作流中枢')).toBeInTheDocument();
    expect(screen.getByText('9 入口')).toBeInTheDocument();

    // 检查三大分类标题
    expect(screen.getByText('任务生命周期')).toBeInTheDocument();
    expect(screen.getByText('协同与网络')).toBeInTheDocument();
    expect(screen.getByText('资产与看板')).toBeInTheDocument();

    // 检查九大入口项目
    expect(screen.getByText('新工作任务')).toBeInTheDocument();
    expect(screen.getByText('定时任务')).toBeInTheDocument();
    expect(screen.getByText('主对话中枢')).toBeInTheDocument();
    expect(screen.getByText('技能与连接器')).toBeInTheDocument();
    expect(screen.getByText('伙伴对话')).toBeInTheDocument();
    expect(screen.getByText('手机遥控电脑')).toBeInTheDocument();
    expect(screen.getByText('云盘与资料空间')).toBeInTheDocument();
    expect(screen.getByText('方案与项目看板')).toBeInTheDocument();
    expect(screen.getByText('最近历史')).toBeInTheDocument();

    // 检查角标与快捷键
    expect(screen.getByText('NEW')).toBeInTheDocument();
    expect(screen.getByText('LIVE')).toBeInTheDocument();
    expect(screen.getByText('Cmd+N')).toBeInTheDocument();
    expect(screen.getByText('Cmd+M')).toBeInTheDocument();
  });

  it('点击导航按钮能切换 activeNavEntryId 并应用激活样式', () => {
    render(<NineEntryNavigationShell />);

    const cronBtn = screen.getByTestId('nine-nav-entry-cron_jobs');
    fireEvent.click(cronBtn);

    expect(useOnDemandConfirmationStore.getState().activeNavEntryId).toBe('cron_jobs');
    expect(cronBtn).toHaveClass('text-white');

    const skillsBtn = screen.getByTestId('nine-nav-entry-skills_mcp');
    fireEvent.click(skillsBtn);

    expect(useOnDemandConfirmationStore.getState().activeNavEntryId).toBe('skills_mcp');
    expect(skillsBtn).toHaveClass('text-white');
  });
});
