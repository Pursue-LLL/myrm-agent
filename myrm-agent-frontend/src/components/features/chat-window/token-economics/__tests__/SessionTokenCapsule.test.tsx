import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { SessionTokenCapsule } from '../SessionTokenCapsule';
import { useTokenEconomicsStore } from '../useTokenEconomicsStore';

describe('SessionTokenCapsule', () => {
  beforeEach(() => {
    act(() => {
      useTokenEconomicsStore.getState().resetStore();
    });
  });

  it('renders default zero usage capsule', () => {
    render(<SessionTokenCapsule />);

    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.getByText('¥0.00')).toBeInTheDocument();
  });

  it('renders formatted tokens and cost when session has usage', () => {
    act(() => {
      useTokenEconomicsStore.getState().recordTokenUsage('chat-abc', 'deepseek-chat', {
        promptTokens: 3000,
        completionTokens: 2000,
        totalTokens: 5000,
      });
    });

    render(<SessionTokenCapsule chatId="chat-abc" />);

    expect(screen.getByText('5.0k')).toBeInTheDocument();
    expect(screen.getByText('¥0.0070')).toBeInTheDocument();
  });

  it('renders compact mode without currency cost', () => {
    act(() => {
      useTokenEconomicsStore.getState().recordTokenUsage('chat-compact', 'gpt-4o', {
        promptTokens: 1000,
        completionTokens: 1000,
        totalTokens: 2000,
      });
    });

    render(<SessionTokenCapsule chatId="chat-compact" compact />);

    expect(screen.getByText('2.0k')).toBeInTheDocument();
    expect(screen.queryByText('$0.01')).not.toBeInTheDocument();
  });

  it('shows and hides tooltip on mouse enter and leave', () => {
    act(() => {
      useTokenEconomicsStore.getState().recordTokenUsage('chat-hover', 'qwen-max', {
        promptTokens: 1200,
        completionTokens: 800,
        totalTokens: 2000,
      });
    });

    const { container } = render(<SessionTokenCapsule chatId="chat-hover" />);

    expect(screen.queryByTestId('token-economics-tooltip')).not.toBeInTheDocument();

    const wrapper = container.firstChild as HTMLElement;
    fireEvent.mouseEnter(wrapper);

    expect(screen.getByTestId('token-economics-tooltip')).toBeInTheDocument();
    expect(screen.getByText('会话 Token 消耗')).toBeInTheDocument();
    expect(screen.getByText('1,200')).toBeInTheDocument();
    expect(screen.getByText('800')).toBeInTheDocument();

    fireEvent.mouseLeave(wrapper);
    expect(screen.queryByTestId('token-economics-tooltip')).not.toBeInTheDocument();
  });

  it('triggers balance modal on button click', () => {
    const onOpenBalanceModal = vi.fn();

    // 1. With custom callback
    const { rerender } = render(
      <SessionTokenCapsule onOpenBalanceModal={onOpenBalanceModal} />,
    );

    const btn = screen.getByTestId('session-token-capsule-button');
    fireEvent.click(btn);
    expect(onOpenBalanceModal).toHaveBeenCalledTimes(1);

    // 2. Default store behavior
    rerender(<SessionTokenCapsule />);
    fireEvent.click(btn);
    expect(useTokenEconomicsStore.getState().isBalanceModalOpen).toBe(true);
  });
});
