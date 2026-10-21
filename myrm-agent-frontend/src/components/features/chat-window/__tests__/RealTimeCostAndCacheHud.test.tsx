/** @vitest-environment jsdom */

/**
 * [INPUT]
 * - @/components/features/chat-window/RealTimeCostAndCacheHud::RealTimeCostAndCacheHud
 * - @/store/useChatStore::useChatStore
 *
 * [OUTPUT]
 * - RealTimeCostAndCacheHud 单元测试套件
 *
 * [POS]
 * tests/components/features/chat-window/__tests__/RealTimeCostAndCacheHud.test.tsx
 * 验证常驻算力胶囊 HUD 的用量计算、Cache 高亮门限与交互行为。
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RealTimeCostAndCacheHud } from '../RealTimeCostAndCacheHud';
import useChatStore from '@/store/useChatStore';
import type { Message } from '@/store/chat/types';

vi.mock('@/services/pricing', () => ({
  fetchModelPricing: vi.fn().mockResolvedValue({
    models: {
      'claude-3-5-sonnet-20241022': {
        model: 'claude-3-5-sonnet-20241022',
        input_cost_per_mtoken: 3.0,
        output_cost_per_mtoken: 15.0,
        cache_read_cost_per_mtoken: 0.3,
        cache_write_cost_per_mtoken: 3.75,
        cache_read_discount: 0.9,
        supports_prompt_caching: true,
      },
    },
  }),
}));

describe('RealTimeCostAndCacheHud Component', () => {
  beforeEach(() => {
    useChatStore.setState({
      messages: [],
      selectedModels: { base: 'claude-3-5-sonnet-20241022', vision: null, reasoning: null },
    });
  });

  it('renders initial standby capsule when no usage is present', () => {
    render(<RealTimeCostAndCacheHud />);
    expect(screen.getByText('算力透视 HUD')).toBeInTheDocument();
  });

  it('renders token watermark without cache badge when cache threshold is not met', () => {
    const mockMsg: Message = {
      messageId: 'msg-1',
      role: 'assistant',
      content: 'Hello',
      usage: {
        prompt_tokens: 500,
        completion_tokens: 100,
        total_tokens: 600,
        cached_tokens: 100, // < 1024 tokens
        net_savings_usd: 0.00002, // < 0.0001 USD
      },
    } as Message;

    useChatStore.setState({ messages: [mockMsg] });

    render(<RealTimeCostAndCacheHud />);
    expect(screen.getByText('600 tok')).toBeInTheDocument();
    // 低于门限时仅显示灰度比率，不触发绿色高亮微徽章
    expect(screen.getByText('20% Cache')).toBeInTheDocument();
    expect(screen.queryByText(/省/)).not.toBeInTheDocument();
  });

  it('renders highlighted cache badge with savings when threshold is effectively met', () => {
    const mockMsg: Message = {
      messageId: 'msg-2',
      role: 'assistant',
      content: 'Cached output',
      usage: {
        prompt_tokens: 20000,
        completion_tokens: 800,
        total_tokens: 20800,
        cached_tokens: 16000, // >= 1024 tokens
        net_savings_usd: 0.0432, // >= 0.0001 USD
        cache_hit_rate: 80.0,
        has_effective_cache: true,
      },
    } as Message;

    useChatStore.setState({ messages: [mockMsg] });

    render(<RealTimeCostAndCacheHud />);
    expect(screen.getByText('20.8K tok')).toBeInTheDocument();
    expect(screen.getByText('80% Cache')).toBeInTheDocument();
    expect(screen.getByText(/\(省 \$0\.043\)/)).toBeInTheDocument();
  });
});
