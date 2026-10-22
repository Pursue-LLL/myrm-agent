import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ConversationalOnboardingWizard } from '../ConversationalOnboardingWizard';
import { ZeroCliQuickLauncherDeck } from '../ZeroCliQuickLauncherDeck';
import { useConversationalOnboardingStore } from '../useConversationalOnboardingStore';

describe('ConversationalOnboardingWizard & ZeroCliQuickLauncherDeck Components', () => {
  beforeEach(() => {
    useConversationalOnboardingStore.getState().resetOnboarding();
  });

  describe('ConversationalOnboardingWizard', () => {
    it('renders greeting message and interactive preset options initially', () => {
      render(<ConversationalOnboardingWizard />);

      expect(screen.getByText(/对话式向导 · 边聊边配/)).toBeDefined();
      expect(screen.getByText(/Zero-CLI 极客脱敏/)).toBeDefined();
      expect(screen.getByText(/代码架构与工程/)).toBeDefined();
      expect(screen.getByText(/营销与竞品洞察/)).toBeDefined();
      expect(screen.getByText(/行政与高效写作/)).toBeDefined();
      expect(screen.getByText(/财务对账与审计/)).toBeDefined();
      expect(screen.getByText(/请先在左侧选择意图或输入您的需求/)).toBeDefined();
    });

    it('generates recipe draft when clicking a preset intent option', () => {
      render(<ConversationalOnboardingWizard />);

      const devOptionBtn = screen.getByText('代码架构与工程').closest('button');
      expect(devOptionBtn).toBeDefined();
      if (devOptionBtn) {
        fireEvent.click(devOptionBtn);
      }

      // 验证右侧出现配方草案
      expect(screen.getByDisplayValue('全栈架构工程师')).toBeDefined();
      expect(screen.getByText('Staff Fullstack Architect')).toBeDefined();
      expect(screen.getByText(/省 Token ~45%/)).toBeDefined();
      expect(screen.getByText('Git 自动化协作流')).toBeDefined();
      expect(screen.getByRole('button', { name: /一键确认并激活伙伴/ })).toBeDefined();
    });

    it('infers recipe from custom natural language input', () => {
      render(<ConversationalOnboardingWizard />);

      const input = screen.getByPlaceholderText(/或者用一句话描述/);
      fireEvent.change(input, { target: { value: '做跨境电商，分析海外社交媒体和舆情' } });

      const sendBtn = screen.getByLabelText('发送需求');
      fireEvent.click(sendBtn);

      expect(screen.getByDisplayValue('增长与营销洞察官')).toBeDefined();
      expect(screen.getByText('Growth & Market Analyst')).toBeDefined();
      expect(screen.getByText('全网舆情与网页抓取')).toBeDefined();
    });

    it('allows editing agent name and toggling model tier before activation', () => {
      render(<ConversationalOnboardingWizard />);

      // 点击行政写作预设
      const adminBtn = screen.getByText('行政与高效写作').closest('button');
      if (adminBtn) {
        fireEvent.click(adminBtn);
      }

      // 修改伙伴名称
      const nameInput = screen.getByDisplayValue('行政文书高效助手');
      fireEvent.change(nameInput, { target: { value: '我的行政大管家' } });
      expect(screen.getByDisplayValue('我的行政大管家')).toBeDefined();

      // 切换算力档位为 Pro
      const proTierBtn = screen.getByRole('button', { name: /Pro \(深度推理\)/ });
      fireEvent.click(proTierBtn);

      // 一键确认并激活伙伴
      const activateBtn = screen.getByRole('button', { name: /一键确认并激活伙伴/ });
      fireEvent.click(activateBtn);

      // 验证切换到就绪界面
      expect(screen.getByText(/恭喜！智能伙伴已成功就绪/)).toBeDefined();
      expect(screen.getByText(/「我的行政大管家」已完成专属技能挂载/)).toBeDefined();

      // 点击重新配置
      const reconfigBtn = screen.getByRole('button', { name: /重新配置/ });
      fireEvent.click(reconfigBtn);
      expect(screen.getByText(/请先在左侧选择意图或输入您的需求/)).toBeDefined();
    });
  });

  describe('ZeroCliQuickLauncherDeck', () => {
    it('renders zero-cli banner, health probes, and launch action buttons', () => {
      const handleLaunchWizard = vi.fn();
      const handleOpenStudio = vi.fn();

      render(
        <ZeroCliQuickLauncherDeck
          onLaunchWizard={handleLaunchWizard}
          onOpenStudio={handleOpenStudio}
        />
      );

      expect(screen.getByText('零终端纯图形化工作台')).toBeDefined();
      expect(screen.getByText('100% GUI-First')).toBeDefined();
      expect(screen.getByText('图形化 Web 工作台')).toBeDefined();
      expect(screen.getByText('原生隔离执行环境')).toBeDefined();
      expect(screen.getByText('智能模型路由通道')).toBeDefined();

      // 点击启动向导
      const launchBtn = screen.getByRole('button', { name: /启动对话式配置向导/ });
      fireEvent.click(launchBtn);
      expect(handleLaunchWizard).toHaveBeenCalledTimes(1);

      // 点击打开智能体工坊
      const studioBtn = screen.getByRole('button', { name: /一站式智能体工坊/ });
      fireEvent.click(studioBtn);
      expect(handleOpenStudio).toHaveBeenCalledTimes(1);
    });
  });
});
