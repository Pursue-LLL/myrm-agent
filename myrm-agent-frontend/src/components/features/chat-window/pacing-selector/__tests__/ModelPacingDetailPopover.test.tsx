import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { useModelPacingStore } from '../useModelPacingStore';
import { ModelPacingDetailPopover } from '../ModelPacingDetailPopover';

describe('ModelPacingDetailPopover', () => {
  beforeEach(() => {
    act(() => {
      useModelPacingStore.getState().resetStore();
    });
  });

  it('renders nothing when popover is closed', () => {
    const { container } = render(<ModelPacingDetailPopover />);
    expect(container.firstChild).toBeNull();
  });

  it('renders all three tiers when open', () => {
    act(() => {
      useModelPacingStore.getState().togglePopover(true);
    });

    render(<ModelPacingDetailPopover />);

    expect(screen.getByRole('region', { name: '模型执行节奏选择' })).toBeInTheDocument();
    expect(screen.getByText('执行节奏档位切换')).toBeInTheDocument();
    expect(screen.getByText('极速日常')).toBeInTheDocument();
    expect(screen.getByText('平衡推荐')).toBeInTheDocument();
    expect(screen.getByText('深度推理')).toBeInTheDocument();

    expect(screen.getByText('< 5s')).toBeInTheDocument();
    expect(screen.getByText('10-25s')).toBeInTheDocument();
    expect(screen.getByText('30-90s')).toBeInTheDocument();
  });

  it('selects tier on card click and triggers callbacks', () => {
    const onTierSelected = vi.fn();
    act(() => {
      useModelPacingStore.getState().togglePopover(true);
    });

    render(
      <ModelPacingDetailPopover
        chatId="chat_prod_101"
        onTierSelected={onTierSelected}
      />,
    );

    // Fast tier button
    const fastBtn = screen.getByRole('button', { name: /极速日常/ });
    fireEvent.click(fastBtn);

    expect(onTierSelected).toHaveBeenCalledWith('fast');
    expect(useModelPacingStore.getState().activeTier).toBe('fast');
    expect(useModelPacingStore.getState().perChatOverrides['chat_prod_101']).toBe('fast');
  });

  it('closes popover on close button click', () => {
    act(() => {
      useModelPacingStore.getState().togglePopover(true);
    });

    render(<ModelPacingDetailPopover />);

    const closeBtn = screen.getByRole('button', { name: '关闭节奏选择器' });
    fireEvent.click(closeBtn);

    expect(useModelPacingStore.getState().isPopoverOpen).toBe(false);
  });
});
