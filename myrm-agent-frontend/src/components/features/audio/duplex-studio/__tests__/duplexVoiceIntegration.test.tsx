import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { HandsFreeDuplexStudioCard } from '../HandsFreeDuplexStudioCard';
import { useDuplexVoiceStore } from '../useDuplexVoiceStore';

describe('DuplexVoice Integration End-to-End', () => {
  beforeEach(() => {
    act(() => {
      useDuplexVoiceStore.getState().reset();
    });
  });

  it('完整走通：开启全双工会话 -> 智能体播报 -> 用户开口插话打断 -> 上下文自愈与截断对齐全流程', () => {
    render(<HandsFreeDuplexStudioCard />);

    expect(
      screen.getByTestId('hands-free-duplex-studio-card')
    ).toBeInTheDocument();

    // 1. 开启全双工通道
    const toggleBtn = screen.getByRole('button', {
      name: /开启全双工免唤醒/i,
    });
    act(() => {
      fireEvent.click(toggleBtn);
    });

    expect(useDuplexVoiceStore.getState().status).toBe('listening');
    expect(screen.getByText('挂断双工通道')).toBeInTheDocument();

    // 2. 模拟智能体开始播报
    const simulateAgentBtn = screen.getByRole('button', {
      name: /模拟 Agent 说话/i,
    });
    act(() => {
      fireEvent.click(simulateAgentBtn);
    });

    expect(useDuplexVoiceStore.getState().status).toBe('speaking');
    expect(
      screen.getByText(/全自动搭建用户中心后端路由/)
    ).toBeInTheDocument();

    // 3. 模拟用户开口插话纠偏
    const input = screen.getByPlaceholderText('模拟开口说话插话内容…');
    const bargeInSubmitBtn = screen.getByRole('button', {
      name: '模拟开口打断',
    });

    fireEvent.change(input, {
      target: { value: '停，不要路由，直接输出单文件代码即可' },
    });
    act(() => {
      fireEvent.click(bargeInSubmitBtn);
    });

    // 4. 验证触发了 Barge-In 打断，并且反馈横幅弹出
    expect(
      screen.getByTestId('barge-in-feedback-banner')
    ).toBeInTheDocument();
    expect(
      screen.getByText('全双工实时插话打断生效 (Zero-Latency Barge-In)')
    ).toBeInTheDocument();

    // 5. 检查对话流中已生成截断的 Agent 消息和用户的纠偏消息
    expect(screen.getByText(/已被用户插话截断/)).toBeInTheDocument();
    expect(
      screen.getByText(/直接输出单文件代码即可/)
    ).toBeInTheDocument();

    // 6. 挂断通道
    const hangupBtn = screen.getByRole('button', {
      name: /挂断双工通道/i,
    });
    act(() => {
      fireEvent.click(hangupBtn);
    });
    expect(useDuplexVoiceStore.getState().status).toBe('idle');
  });

  it('支持在设置面板中调整打断灵敏度与环境降噪开关', () => {
    render(<HandsFreeDuplexStudioCard />);

    const openSettingsBtn = screen.getByRole('button', {
      name: '打开双工设置',
    });

    // 打开设置抽屉
    act(() => {
      fireEvent.click(openSettingsBtn);
    });
    expect(screen.getByTestId('duplex-settings-drawer')).toBeInTheDocument();

    // 切换打断灵敏度为 HIGH
    const highBtn = screen.getByRole('button', { name: 'HIGH' });
    act(() => {
      fireEvent.click(highBtn);
    });
    expect(useDuplexVoiceStore.getState().settings.bargeInSensitivity).toBe(
      'high'
    );

    // 切换环境降噪复选框
    const checkbox = screen.getByRole('checkbox');
    expect(checkbox).toBeChecked();
    act(() => {
      fireEvent.click(checkbox);
    });
    expect(
      useDuplexVoiceStore.getState().settings.noiseSuppressionEnabled
    ).toBe(false);

    // 再次点击关闭设置抽屉
    act(() => {
      fireEvent.click(openSettingsBtn);
    });
    expect(
      screen.queryByTestId('duplex-settings-drawer')
    ).not.toBeInTheDocument();
  });

  it('支持点击重置按钮还原全双工状态', () => {
    render(<HandsFreeDuplexStudioCard />);

    act(() => {
      useDuplexVoiceStore.getState().startDuplexSession();
    });
    expect(useDuplexVoiceStore.getState().status).toBe('listening');

    const resetBtn = screen.getByRole('button', { name: '重置双工状态' });
    act(() => {
      fireEvent.click(resetBtn);
    });

    expect(useDuplexVoiceStore.getState().status).toBe('idle');
  });
});
