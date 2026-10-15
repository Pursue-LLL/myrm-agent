import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { UnifiedAgentStudioModal } from '../UnifiedAgentStudioModal';
import { FullModalityParityCallHUD } from '../FullModalityParityCallHUD';
import { useFingerprintStudioStore } from '../useFingerprintStudioStore';

describe('UnifiedAgentStudioModal & FullModalityParityCallHUD Components', () => {
  beforeEach(() => {
    useFingerprintStudioStore.getState().resetAll();
  });

  describe('UnifiedAgentStudioModal', () => {
    it('does not render when isStudioModalOpen is false', () => {
      render(<UnifiedAgentStudioModal />);
      expect(screen.queryByText(/统一智能体工坊/)).toBeNull();
    });

    it('renders studio modal with agent list and tab navigation when open', () => {
      useFingerprintStudioStore.getState().openStudio('agent_fullstack');
      render(<UnifiedAgentStudioModal />);

      expect(screen.getByText(/统一智能体工坊/)).toBeDefined();
      expect(screen.getByText('全栈架构专家')).toBeDefined();
      expect(screen.getByRole('button', { name: /设定与宿主机/ })).toBeDefined();
      expect(screen.getByRole('button', { name: /专属技能/ })).toBeDefined();
      expect(screen.getByRole('button', { name: /数据连接器/ })).toBeDefined();
      expect(screen.getByRole('button', { name: /专属知识库/ })).toBeDefined();
    });

    it('creates a new agent and binds skills interactively', () => {
      useFingerprintStudioStore.getState().openStudio('agent_fullstack');
      render(<UnifiedAgentStudioModal />);

      // 新建智能体
      const input = screen.getByPlaceholderText('智能体名称...');
      fireEvent.change(input, { target: { value: '自动化测试助手' } });
      const createBtn = screen.getByRole('button', { name: /新建智能体伙伴/ });
      fireEvent.click(createBtn);

      expect(screen.getByText('自动化测试助手')).toBeDefined();

      // 切换到技能 Tab
      const skillsTab = screen.getByRole('button', { name: /专属技能/ });
      fireEvent.click(skillsTab);

      expect(screen.getByText('Git 自动化流')).toBeDefined();
      const mountBtn = screen.getAllByRole('button', { name: '挂载技能' })[0];
      fireEvent.click(mountBtn);

      // 验证已切换为解绑
      expect(screen.getByRole('button', { name: '解绑技能' })).toBeDefined();
    });

    it('closes studio when close button is clicked', () => {
      useFingerprintStudioStore.getState().openStudio('agent_fullstack');
      render(<UnifiedAgentStudioModal />);

      const closeButtons = screen.getAllByRole('button');
      const closeBtn = closeButtons[0]; // 头部右上角 X 按钮
      fireEvent.click(closeBtn);

      expect(useFingerprintStudioStore.getState().isStudioModalOpen).toBe(false);
    });
  });

  describe('FullModalityParityCallHUD', () => {
    it('does not render when call session is idle', () => {
      render(<FullModalityParityCallHUD />);
      expect(screen.queryByText('智能体通话')).toBeNull();
    });

    it('renders call HUD in enterprise mode with parity compliance badge', () => {
      useFingerprintStudioStore.getState().startCall('agent_fullstack', '全栈架构专家');
      render(<FullModalityParityCallHUD />);

      expect(screen.getByText('全栈架构专家')).toBeDefined();
      expect(screen.getByText(/企业平权·合规审计/)).toBeDefined();
      expect(screen.getByText('审计链实时存证')).toBeDefined();
      expect(screen.getByText(/全双工通话中/)).toBeDefined();
    });

    it('controls mute, speaker, screen sharing and hang up', () => {
      useFingerprintStudioStore.getState().startCall('agent_fullstack', '全栈架构专家');
      render(<FullModalityParityCallHUD />);

      // 静音
      const muteBtn = screen.getByLabelText('麦克风静音');
      fireEvent.click(muteBtn);
      expect(screen.getByLabelText('取消静音')).toBeDefined();

      // 扬声器
      const speakerBtn = screen.getByLabelText('关闭扬声器');
      fireEvent.click(speakerBtn);
      expect(screen.getByLabelText('开启扬声器')).toBeDefined();

      // 屏幕共享
      const shareBtn = screen.getByLabelText('开始屏幕共享');
      fireEvent.click(shareBtn);
      expect(screen.getByText(/屏幕协同中/)).toBeDefined();

      // 挂断
      const hangupBtn = screen.getByLabelText('挂断通话');
      fireEvent.click(hangupBtn);
      expect(useFingerprintStudioStore.getState().callSession.state).toBe('ended');
    });

    it('renders personal mode without compliance trail but full feature parity', () => {
      useFingerprintStudioStore.getState().setEnterpriseMode(false);
      useFingerprintStudioStore.getState().startCall('agent_fullstack', '全栈架构专家');
      render(<FullModalityParityCallHUD />);

      expect(screen.getByText('全栈架构专家')).toBeDefined();
      expect(screen.getByText(/个人模式/)).toBeDefined();
      expect(screen.queryByText('审计链实时存证')).toBeNull();
    });
  });
});
