import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SideChatTriggerButton } from '../SideChatTriggerButton';
import { useSideChatStore } from '../useSideChatStore';

describe('SideChatTriggerButton', () => {
  beforeEach(() => {
    useSideChatStore.getState().reset();
  });

  it('正常渲染触发按钮文本与图标', () => {
    render(<SideChatTriggerButton />);

    expect(screen.getByTestId('side-chat-trigger-button')).toBeInTheDocument();
    expect(screen.getByText('支线对话')).toBeInTheDocument();
  });

  it('当存在待吸收微调时，展示琥珀色微调数量徽标', () => {
    useSideChatStore.setState({
      steeringQueue: [
        {
          id: 'st-1',
          sourceMessageId: 'm-1',
          intentType: 'incremental_feature',
          content: '导出 Excel',
          priority: 8,
          status: 'pending',
          createdAt: Date.now(),
        },
      ],
    });

    render(<SideChatTriggerButton />);

    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('点击按钮切换抽屉开闭状态', () => {
    render(<SideChatTriggerButton />);

    const button = screen.getByTestId('side-chat-trigger-button');
    fireEvent.click(button);

    expect(useSideChatStore.getState().isOpen).toBe(true);

    fireEvent.click(button);
    expect(useSideChatStore.getState().isOpen).toBe(false);
  });
});
