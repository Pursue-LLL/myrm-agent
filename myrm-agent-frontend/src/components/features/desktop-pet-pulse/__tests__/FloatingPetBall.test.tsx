import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FloatingPetBall } from '../FloatingPetBall';
import { useDesktopPetPulseStore } from '../useDesktopPetPulseStore';

describe('FloatingPetBall', () => {
  beforeEach(() => {
    useDesktopPetPulseStore.getState().resetAll();
  });

  it('正确渲染桌宠球主体、光晕环与智能体胶囊标签', () => {
    render(<FloatingPetBall />);
    expect(screen.getByTestId('desktop-floating-pet-ball')).toBeInTheDocument();
    expect(screen.getByTestId('pet-halo-ring')).toBeInTheDocument();
    expect(screen.getByTestId('pet-main-avatar-button')).toBeInTheDocument();
    expect(screen.getByTestId('pet-identity-capsule')).toHaveTextContent(
      'Myrm 灵动助手'
    );
  });

  it('点击主球切换快捷抽屉展开状态', () => {
    render(<FloatingPetBall />);
    const avatarBtn = screen.getByTestId('pet-main-avatar-button');
    expect(
      useDesktopPetPulseStore.getState().isQuickActionOpen
    ).toBe(false);

    fireEvent.click(avatarBtn);
    expect(
      useDesktopPetPulseStore.getState().isQuickActionOpen
    ).toBe(true);
  });

  it('双击桌宠球触发主工作台唤醒', () => {
    const handleDoubleClick = vi.fn();
    render(<FloatingPetBall onDoubleClick={handleDoubleClick} />);
    const avatarBtn = screen.getByTestId('pet-main-avatar-button');

    fireEvent.doubleClick(avatarBtn);
    expect(handleDoubleClick).toHaveBeenCalledTimes(1);
    expect(
      useDesktopPetPulseStore.getState().mainWindowFocusedCount
    ).toBeGreaterThan(0);
  });

  it('点击暂停按钮切换暂停状态', () => {
    render(<FloatingPetBall />);
    const pauseBtn = screen.getByTestId('pet-pause-shortcut-btn');
    expect(useDesktopPetPulseStore.getState().isPaused).toBe(false);

    fireEvent.click(pauseBtn);
    expect(useDesktopPetPulseStore.getState().isPaused).toBe(true);
    expect(screen.getByTestId('pet-paused-indicator')).toBeInTheDocument();
  });

  it('点击语音直通和数据迁移快捷按钮', () => {
    const handleVoice = vi.fn();
    const handleMigration = vi.fn();
    render(
      <FloatingPetBall
        onVoiceClick={handleVoice}
        onMigrationClick={handleMigration}
      />
    );

    fireEvent.click(screen.getByTestId('pet-voice-shortcut-btn'));
    expect(handleVoice).toHaveBeenCalledTimes(1);
    expect(useDesktopPetPulseStore.getState().isVoiceInputActive).toBe(true);

    fireEvent.click(screen.getByTestId('pet-migration-shortcut-btn'));
    expect(handleMigration).toHaveBeenCalledTimes(1);
    expect(useDesktopPetPulseStore.getState().isMigrationModalOpen).toBe(true);
  });

  it('存在并发次要智能体时渲染轻量堆叠徽标', () => {
    useDesktopPetPulseStore.setState({
      allAgents: [
        {
          agentId: 'default-assistant',
          name: '主智能体',
          colorTheme: '#3b82f6',
          isPrimary: true,
        },
        {
          agentId: 'sub-agent-1',
          name: '次级爬虫',
          colorTheme: '#10b981',
          isPrimary: false,
        },
      ],
      activeQueue: [{ agentId: 'sub-agent-1', status: 'queued' }],
    });

    render(<FloatingPetBall />);
    const badge = screen.getByTestId('pet-stacked-agent-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent('+1');
  });
});
