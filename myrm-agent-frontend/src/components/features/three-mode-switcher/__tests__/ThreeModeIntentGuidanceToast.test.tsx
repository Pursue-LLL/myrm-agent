import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThreeModeIntentGuidanceToast } from '../ThreeModeIntentGuidanceToast';
import { useThreeModeStore } from '../useThreeModeStore';

describe('ThreeModeIntentGuidanceToast 组件单测', () => {
  beforeEach(() => {
    useThreeModeStore.setState({
      currentMode: 'ask',
      intentGuidance: {
        hasWriteIntent: true,
        matchedKeywords: ['保存到'],
        suggestedMode: 'craft',
        guidanceMessage: '检测到写操作意图，建议切换为 Craft 做一做',
      },
    });
  });

  it('当没有写意图时不渲染任何 Toast 内容', () => {
    useThreeModeStore.setState({ intentGuidance: null });
    const { container } = render(<ThreeModeIntentGuidanceToast />);

    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('three-mode-intent-guidance-toast')).not.toBeInTheDocument();
  });

  it('当存在写意图时正确渲染提示卡片与文案', () => {
    render(<ThreeModeIntentGuidanceToast />);

    expect(screen.getByTestId('three-mode-intent-guidance-toast')).toBeInTheDocument();
    expect(screen.getByText('写操作意图提醒')).toBeInTheDocument();
    expect(screen.getByText('只读保护中')).toBeInTheDocument();
    expect(screen.getByText('检测到写操作意图，建议切换为 Craft 做一做')).toBeInTheDocument();
  });

  it('点击「一键切换为 Craft 做一做」能成功热换挡并解除提示', () => {
    render(<ThreeModeIntentGuidanceToast />);

    const switchBtn = screen.getByText(/一键切换为 Craft 做一做/);
    fireEvent.click(switchBtn);

    expect(useThreeModeStore.getState().currentMode).toBe('craft');
    expect(useThreeModeStore.getState().intentGuidance).toBeNull();
  });

  it('点击「保持问一问」或关闭按钮能关闭提示气泡且保持当前模式', () => {
    render(<ThreeModeIntentGuidanceToast />);

    const dismissBtn = screen.getByText('保持问一问');
    fireEvent.click(dismissBtn);

    expect(useThreeModeStore.getState().currentMode).toBe('ask');
    expect(useThreeModeStore.getState().intentGuidance).toBeNull();
  });
});
