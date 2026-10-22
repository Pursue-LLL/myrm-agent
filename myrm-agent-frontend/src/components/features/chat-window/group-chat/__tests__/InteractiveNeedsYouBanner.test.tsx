/** @vitest-environment jsdom */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { InteractiveNeedsYouBanner } from '../InteractiveNeedsYouBanner';
import type { NeedsYouIntervention } from '../groupChatTypes';

const mockIntervention: NeedsYouIntervention = {
  threadId: 'th-deadlock-99',
  issueTitle: '核心认证鉴权方案产生分歧',
  contextSummary: '架构总监主张 JWT 无状态 Token，安全官认为必须使用 Redis 严格黑名单与刷新令牌。',
  suggestedOptions: ['采纳 JWT 方案', '采纳 Redis 黑名单方案', '折中：带短有效期的双令牌'],
};

describe('InteractiveNeedsYouBanner Component', () => {
  it('does not render when intervention is null', () => {
    const { container } = render(
      <InteractiveNeedsYouBanner
        intervention={null}
        onIntervene={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders issue title, context summary and suggested options', () => {
    render(
      <InteractiveNeedsYouBanner
        intervention={mockIntervention}
        onIntervene={vi.fn()}
      />,
    );

    expect(screen.getByTestId('interactive-needs-you-banner')).toBeDefined();
    expect(screen.getByText('核心认证鉴权方案产生分歧')).toBeDefined();
    expect(screen.getByText(/架构总监主张 JWT/i)).toBeDefined();
    expect(screen.getByText('采纳 JWT 方案')).toBeDefined();
    expect(screen.getByText('采纳 Redis 黑名单方案')).toBeDefined();
  });

  it('triggers onIntervene immediately when suggested option chip is clicked', () => {
    const onInterveneMock = vi.fn();

    render(
      <InteractiveNeedsYouBanner
        intervention={mockIntervention}
        onIntervene={onInterveneMock}
      />,
    );

    const chipBtn = screen.getByTestId('needs-you-chip-采纳 JWT 方案');
    fireEvent.click(chipBtn);

    expect(onInterveneMock).toHaveBeenCalledWith('采纳 JWT 方案');
  });

  it('submits custom decision instruction via input and submit button', () => {
    const onInterveneMock = vi.fn();

    render(
      <InteractiveNeedsYouBanner
        intervention={mockIntervention}
        onIntervene={onInterveneMock}
      />,
    );

    const input = screen.getByPlaceholderText(/专属决断指令|customResponse/i);
    fireEvent.change(input, { target: { value: '先使用 JWT 快速验证，后期再接入 Redis' } });

    const submitBtn = screen.getByTestId('needs-you-submit-btn');
    fireEvent.click(submitBtn);

    expect(onInterveneMock).toHaveBeenCalledWith('先使用 JWT 快速验证，后期再接入 Redis');
  });

  it('submits custom decision on Enter key', () => {
    const onInterveneMock = vi.fn();

    render(
      <InteractiveNeedsYouBanner
        intervention={mockIntervention}
        onIntervene={onInterveneMock}
      />,
    );

    const input = screen.getByPlaceholderText(/专属决断指令|customResponse/i);
    fireEvent.change(input, { target: { value: '采纳短有效期的双令牌' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onInterveneMock).toHaveBeenCalledWith('采纳短有效期的双令牌');
  });

  it('calls onDismiss when close button is clicked', () => {
    const onDismissMock = vi.fn();

    render(
      <InteractiveNeedsYouBanner
        intervention={mockIntervention}
        onIntervene={vi.fn()}
        onDismiss={onDismissMock}
      />,
    );

    const closeBtn = screen.getByRole('button', { name: '关闭提示' });
    fireEvent.click(closeBtn);

    expect(onDismissMock).toHaveBeenCalledTimes(1);
  });
});
