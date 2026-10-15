import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CompanionFloatingPet } from '../CompanionFloatingPet';
import { useFloatingPetStore } from '../useFloatingPetStore';

describe('CompanionFloatingPet', () => {
  beforeEach(() => {
    useFloatingPetStore.getState().reset();
  });

  it('初始状态正常渲染灵动挂件与 Bot 图标', () => {
    render(<CompanionFloatingPet />);

    expect(screen.getByTestId('companion-floating-pet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '桌面伴随灵动挂件' })).toBeInTheDocument();
  });

  it('按住挂件开始语音录音，松开发射后台任务', () => {
    render(<CompanionFloatingPet />);

    const petButton = screen.getByRole('button', { name: '桌面伴随灵动挂件' });

    // 1. 模拟按下 (MouseDown)
    fireEvent.mouseDown(petButton);
    expect(useFloatingPetStore.getState().isVoiceRecording).toBe(true);
    expect(useFloatingPetStore.getState().mood).toBe('listening');

    // 2. 模拟松开 (MouseUp)
    fireEvent.mouseUp(petButton);
    expect(useFloatingPetStore.getState().isVoiceRecording).toBe(false);
    expect(useFloatingPetStore.getState().mood).toBe('thinking');
    expect(useFloatingPetStore.getState().activeTask).not.toBeNull();
    expect(useFloatingPetStore.getState().isBubbleExpanded).toBe(true);
  });

  it('点击球体切换迷你气泡的展开与折叠', () => {
    useFloatingPetStore.setState({
      activeTask: {
        id: 'task-1',
        title: '测试任务',
        status: 'running',
        progress: 30,
        summary: '摘要',
        createdAt: Date.now(),
      },
      isBubbleExpanded: false,
    });

    render(<CompanionFloatingPet />);

    const petButton = screen.getByRole('button', { name: '桌面伴随灵动挂件' });
    fireEvent.click(petButton);

    expect(useFloatingPetStore.getState().isBubbleExpanded).toBe(true);

    fireEvent.click(petButton);
    expect(useFloatingPetStore.getState().isBubbleExpanded).toBe(false);
  });

  it('当存在活跃任务时展示外置进度百分比微徽标', () => {
    useFloatingPetStore.setState({
      activeTask: {
        id: 'task-1',
        title: '正在编译',
        status: 'running',
        progress: 68,
        summary: '编译中',
        createdAt: Date.now(),
      },
    });

    render(<CompanionFloatingPet />);

    expect(screen.getByText('68%')).toBeInTheDocument();
  });
});
