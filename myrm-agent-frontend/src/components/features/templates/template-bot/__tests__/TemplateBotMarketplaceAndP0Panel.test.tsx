import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TemplateBotMarketplaceModal } from '../TemplateBotMarketplaceModal';
import { P0UrgencyCruiseControlPanel } from '../P0UrgencyCruiseControlPanel';
import { useTemplateBotStore } from '../useTemplateBotStore';

describe('TemplateBotMarketplaceModal & P0UrgencyCruiseControlPanel', () => {
  beforeEach(() => {
    useTemplateBotStore.getState().resetToDefaults();
    vi.restoreAllMocks();
  });

  describe('TemplateBotMarketplaceModal', () => {
    it('未打开时不渲染弹窗主体', () => {
      const { container } = render(<TemplateBotMarketplaceModal />);
      expect(container.firstChild).toBeNull();
    });

    it('打开时正确渲染大盘、分类Tab、团队预设与岗位卡片', () => {
      useTemplateBotStore.getState().setMarketplaceModalOpen(true);
      render(<TemplateBotMarketplaceModal />);

      expect(
        screen.getByTestId('template-bot-modal-content')
      ).toBeInTheDocument();
      expect(
        screen.getByText('岗位智能体模板市场 (TemplateBot Hub)')
      ).toBeInTheDocument();
      expect(screen.getByTestId('category-tab-all')).toBeInTheDocument();
      expect(screen.getByTestId('category-tab-engineering')).toBeInTheDocument();

      // 预置团队卡片
      expect(
        screen.getByTestId('team-roster-card-team-tech-delivery')
      ).toBeInTheDocument();

      // 岗位卡片
      expect(
        screen.getByTestId('template-bot-card-bot-chief-of-staff')
      ).toBeInTheDocument();
      expect(
        screen.getByTestId('template-bot-card-bot-senior-architect')
      ).toBeInTheDocument();
    });

    it('搜索框与分类 Tab 能够动态筛选岗位智能体', () => {
      useTemplateBotStore.getState().setMarketplaceModalOpen(true);
      render(<TemplateBotMarketplaceModal />);

      const searchInput = screen.getByTestId('template-search-input');
      fireEvent.change(searchInput, { target: { value: '财务' } });

      expect(
        screen.getByTestId('template-bot-card-bot-financial-analyst')
      ).toBeInTheDocument();
      expect(
        screen.queryByTestId('template-bot-card-bot-senior-architect')
      ).toBeNull();
    });

    it('一键克隆团队架构能够批量实例化所有岗位', () => {
      useTemplateBotStore.getState().setMarketplaceModalOpen(true);
      render(<TemplateBotMarketplaceModal />);

      const cloneBtn = screen.getByTestId('clone-team-btn-team-tech-delivery');
      fireEvent.click(cloneBtn);

      const state = useTemplateBotStore.getState();
      expect(state.clonedTeamRosters).toHaveLength(1);
      expect(state.instantiatedBotIds).toContain('bot-chief-of-staff');
      expect(state.instantiatedBotIds).toContain('bot-senior-architect');
    });

    it('单岗位实例化后按钮变为就绪禁用状态', () => {
      useTemplateBotStore.getState().setMarketplaceModalOpen(true);
      render(<TemplateBotMarketplaceModal />);

      const instantiateBtn = screen.getByTestId(
        'instantiate-bot-btn-bot-chief-of-staff'
      );
      fireEvent.click(instantiateBtn);

      expect(
        useTemplateBotStore.getState().instantiatedBotIds
      ).toContain('bot-chief-of-staff');
      expect(instantiateBtn).toHaveTextContent('已实例化就绪');
      expect(instantiateBtn).toBeDisabled();
    });

    it('点击关闭按钮或按 Escape 键能够关闭大盘', () => {
      useTemplateBotStore.getState().setMarketplaceModalOpen(true);
      render(<TemplateBotMarketplaceModal />);

      const closeBtn = screen.getByTestId('close-marketplace-modal-btn');
      fireEvent.click(closeBtn);

      expect(useTemplateBotStore.getState().isMarketplaceModalOpen).toBe(false);
    });
  });

  describe('P0UrgencyCruiseControlPanel', () => {
    it('未激活时渲染紧凑触发按钮', () => {
      render(<P0UrgencyCruiseControlPanel />);

      expect(
        screen.getByTestId('p0-urgency-inactive-container')
      ).toBeInTheDocument();
      expect(screen.getByTestId('activate-p0-urgency-btn')).toHaveTextContent(
        'P0 紧急模式'
      );
    });

    it('激活后展开巡航面板、倒计时与拦截计数', () => {
      render(<P0UrgencyCruiseControlPanel />);

      const activateBtn = screen.getByTestId('activate-p0-urgency-btn');
      fireEvent.click(activateBtn);

      expect(
        screen.getByTestId('p0-urgency-cruise-panel')
      ).toBeInTheDocument();
      expect(
        screen.getByText('P0 紧急高频巡航模式已激活')
      ).toBeInTheDocument();
      expect(screen.getByTestId('watchdog-countdown-text')).toBeInTheDocument();
      expect(screen.getByTestId('deviation-count-badge')).toHaveTextContent('0');
      expect(screen.getByTestId('steering-count-badge')).toHaveTextContent('0');
    });

    it('点击立即巡检能够触发一次看门狗审查', () => {
      useTemplateBotStore.getState().activateP0UrgencyMode('task-01');
      render(<P0UrgencyCruiseControlPanel />);

      const manualInspectBtn = screen.getByTestId(
        'trigger-manual-inspection-btn'
      );
      fireEvent.click(manualInspectBtn);

      expect(
        useTemplateBotStore.getState().p0CruiseState.watchdogLogs
      ).toHaveLength(1);
    });

    it('点击展开抽屉按钮能够切换看门狗日志可见性', () => {
      useTemplateBotStore.getState().activateP0UrgencyMode('task-01');
      useTemplateBotStore.getState().runWatchdogInspection();

      render(<P0UrgencyCruiseControlPanel />);

      const toggleLogsBtn = screen.getByTestId('toggle-watchdog-logs-btn');
      fireEvent.click(toggleLogsBtn);

      expect(screen.getByTestId('watchdog-logs-drawer')).toBeInTheDocument();

      fireEvent.click(toggleLogsBtn);
      expect(screen.queryByTestId('watchdog-logs-drawer')).toBeNull();
    });

    it('点击退出按钮恢复未激活态', () => {
      useTemplateBotStore.getState().activateP0UrgencyMode('task-01');
      render(<P0UrgencyCruiseControlPanel />);

      const deactivateBtn = screen.getByTestId('deactivate-p0-btn');
      fireEvent.click(deactivateBtn);

      expect(useTemplateBotStore.getState().p0CruiseState.isActive).toBe(false);
      expect(
        screen.getByTestId('p0-urgency-inactive-container')
      ).toBeInTheDocument();
    });
  });
});
