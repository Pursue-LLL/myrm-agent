import React from 'react';
import { render, screen, fireEvent, act, within } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { TeamRuntimeMultiSurfaceCockpit } from '../TeamRuntimeMultiSurfaceCockpit';
import { useTeamRuntimeStore } from '../useTeamRuntimeStore';

describe('TeamRuntimeMultiSurfaceCockpit', () => {
  beforeEach(() => {
    act(() => {
      useTeamRuntimeStore.getState().resetTeamRuntimeState();
    });
  });

  it('renders team runtime cockpit with top bar, DAG canvas, and telemetry card', () => {
    render(<TeamRuntimeMultiSurfaceCockpit />);

    expect(screen.getByRole('region', { name: '数字团队运行驾驶舱' })).toBeInTheDocument();
    expect(screen.getByText('政企智能调度数字专家团')).toBeInTheDocument();
    expect(screen.getByText('团队 DAG 反应式依赖拓扑画布')).toBeInTheDocument();
    expect(screen.getByText('数字团队协同减负度量大盘')).toBeInTheDocument();

    // Verify all 5 DAG nodes
    expect(screen.getByText('需求剖析与总控')).toBeInTheDocument();
    expect(screen.getByText('高可用技术方案')).toBeInTheDocument();
    expect(screen.getByText('财务报价与预算核算')).toBeInTheDocument();
    expect(screen.getByText('合规与数据出境审查')).toBeInTheDocument();
    expect(screen.getByText('投标文件与合同终稿')).toBeInTheDocument();
  });

  it('opens drawer on node selection and displays contract facts and exceptions', () => {
    render(<TeamRuntimeMultiSurfaceCockpit />);

    const architectNodeBtn = screen.getByRole('button', { name: /高可用技术方案/i });
    fireEvent.click(architectNodeBtn);

    const drawer = screen.getByRole('complementary', { name: '交付物契约与例外检查抽屉' });
    expect(drawer).toBeInTheDocument();
    expect(within(drawer).getByText(/同城双活双中心部署方案/i)).toBeInTheDocument();
    expect(within(drawer).getByText('已决事实列表 (Decided Facts)')).toBeInTheDocument();
    expect(within(drawer).getByText('未决风险与排除条款 (Exceptions)')).toBeInTheDocument();
  });

  it('simulates deliverable update and triggers downstream stale prerequisite badge', () => {
    render(<TeamRuntimeMultiSurfaceCockpit />);

    // Open architect node
    const architectNodeBtn = screen.getByRole('button', { name: /高可用技术方案/i });
    fireEvent.click(architectNodeBtn);

    const drawer = screen.getByRole('complementary', { name: '交付物契约与例外检查抽屉' });
    const updateBtn = within(drawer).getByRole('button', { name: '递增版本并广播下游前提失效' });
    fireEvent.click(updateBtn);

    // Downstream compliance node should now have stale prerequisite badge
    expect(screen.getAllByText('前提已失效').length).toBeGreaterThan(0);
    expect(screen.getByText(/2 个节点前提失效已自动拦截/i)).toBeInTheDocument();
  });

  it('opens conflict resolution modal and arbitrates a decision', () => {
    render(<TeamRuntimeMultiSurfaceCockpit />);

    // Open conflict modal from top bar
    const conflictBtn = screen.getByRole('button', { name: /待仲裁矛盾/i });
    fireEvent.click(conflictBtn);

    const modal = screen.getByRole('dialog', { name: '数字团队不可调和矛盾仲裁卡片' });
    expect(modal).toBeInTheDocument();
    expect(within(modal).getByText(/高可用双活方案 vs 财务预算硬顶冲突/i)).toBeInTheDocument();

    // Arbitrate option 1
    const arbitrateBtn = within(modal).getAllByRole('button', { name: '拍板此方案' })[0];
    fireEvent.click(arbitrateBtn);

    expect(within(modal).getByText('已采纳为法定基准')).toBeInTheDocument();

    // Close modal
    const closeBtn = within(modal).getByRole('button', { name: '完成并关闭' });
    fireEvent.click(closeBtn);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('closes drawer when close button is clicked', () => {
    render(<TeamRuntimeMultiSurfaceCockpit />);

    const leaderNodeBtn = screen.getByRole('button', { name: /需求剖析与总控/i });
    fireEvent.click(leaderNodeBtn);

    expect(screen.getByRole('complementary', { name: '交付物契约与例外检查抽屉' })).toBeInTheDocument();

    const closeDrawerBtn = screen.getByRole('button', { name: '关闭交付物抽屉' });
    fireEvent.click(closeDrawerBtn);

    expect(screen.queryByRole('complementary', { name: '交付物契约与例外检查抽屉' })).not.toBeInTheDocument();
  });
});
