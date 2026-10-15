import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AdoptSynthesizeBar } from '../AdoptSynthesizeBar';
import { useArenaStore } from '../useArenaStore';

describe('AdoptSynthesizeBar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useArenaStore.getState().resetStore();
  });

  it('在无内容时按钮处于禁用状态', () => {
    render(<AdoptSynthesizeBar />);

    const buttons = screen.getAllByRole('button');
    for (const btn of buttons) {
      expect(btn).toBeDisabled();
    }
  });

  it('产生流式输出后，点击单模型采纳按钮能触发 adoptSingleSolution', () => {
    useArenaStore.getState().updateStream('claude-3-7-thinking', {
      contentText: '这是 Claude 产出的高质量架构设计',
    });

    render(<AdoptSynthesizeBar />);

    const adoptClaudeBtn = screen.getByRole('button', { name: /采纳 Claude/i });
    expect(adoptClaudeBtn).not.toBeDisabled();

    fireEvent.click(adoptClaudeBtn);
    expect(useArenaStore.getState().adoptedDecision?.chosenModelId).toBe('claude-3-7-thinking');
  });

  it('点击融合双模长板能触发 synthesizeSolutions 与外部回调', () => {
    useArenaStore.getState().setPromptQuery('请设计秒杀防超卖架构');
    useArenaStore.getState().updateStream('claude-3-7-thinking', {
      contentText: '方案一：Redis Lua 预扣库存',
    });
    useArenaStore.getState().updateStream('deepseek-r1', {
      contentText: '方案二：RocketMQ 事务消息最终一致',
    });

    const handleSynthesize = vi.fn();
    render(<AdoptSynthesizeBar onSynthesizeRequested={handleSynthesize} />);

    const synthBtn = screen.getByRole('button', { name: /融合双模长板/i });
    expect(synthBtn).not.toBeDisabled();

    fireEvent.click(synthBtn);

    expect(handleSynthesize).toHaveBeenCalledTimes(1);
    expect(useArenaStore.getState().adoptedDecision?.mode).toBe('synthesize');
    expect(useArenaStore.getState().adoptedDecision?.chosenModelId).toBe('synthesized');
  });
});
