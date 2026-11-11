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
 * 验证常驻算力胶囊 HUD 的用量累计、Cache 高亮门限、金额与 Token 缩写、以及单价弹窗拿到的模型名。
 */

import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { RealTimeCostAndCacheHud } from '../RealTimeCostAndCacheHud';
import useChatStore from '@/store/useChatStore';
import { fetchModelPricing } from '@/services/pricing';
import type { Message, TokenUsage } from '@/store/chat/types';

const stableT = (key: string, values?: Record<string, unknown>) =>
  values ? `${key}:${Object.values(values).join('/')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

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

const MODEL = 'claude-3-5-sonnet-20241022';
const HIGHLIGHT = 'border-emerald-500/30';

let nextMessageId = 0;

/** One turn of the conversation; `usage` fills the token counts the server did not report with zeros. */
function turn(usage?: Partial<TokenUsage>, role: Message['role'] = 'assistant'): Message {
  nextMessageId += 1;
  return {
    messageId: `message-${nextMessageId}`,
    chatId: 'chat-1',
    role,
    content: '',
    createdAt: new Date(),
    usage: usage && { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, ...usage },
  };
}

const showTurns = (...turns: Message[]) => useChatStore.setState({ messages: turns });
const capsule = () => screen.getByRole('button');

describe('RealTimeCostAndCacheHud Component', () => {
  beforeEach(() => {
    vi.mocked(fetchModelPricing).mockClear();
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    useChatStore.setState({
      messages: [],
      selectedModels: { base: MODEL, vision: null, reasoning: null },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('standby', () => {
    it('renders initial standby capsule when no usage is present', () => {
      render(<RealTimeCostAndCacheHud />);
      expect(screen.getByText('idleLabel')).toBeInTheDocument();
    });

    it('stays on standby while no turn has used a token', () => {
      showTurns(turn(undefined, 'user'), turn({ total_tokens: 0 }));

      render(<RealTimeCostAndCacheHud />);

      expect(screen.getByText('idleLabel')).toBeInTheDocument();
      expect(capsule()).not.toHaveClass(HIGHLIGHT);
    });
  });

  describe('token watermark', () => {
    it('adds up the whole conversation and skips turns that report no usage', () => {
      showTurns(
        turn(undefined, 'user'),
        turn({ total_tokens: 300 }),
        turn(undefined, 'user'),
        turn({ total_tokens: 700 }),
      );

      render(<RealTimeCostAndCacheHud />);

      expect(screen.getByText('1.0K tok')).toBeInTheDocument();
    });

    it.each([
      [999, '999 tok'],
      [1_000, '1.0K tok'],
      [20_800, '20.8K tok'],
      [1_240_000, '1.2M tok'],
    ])('abbreviates %i tokens as "%s"', (total, label) => {
      showTurns(turn({ total_tokens: total }));

      render(<RealTimeCostAndCacheHud />);

      expect(screen.getByText(label)).toBeInTheDocument();
    });

    it('shows no cache figure when the reply read nothing from the cache', () => {
      showTurns(turn({ prompt_tokens: 400, total_tokens: 500 }));

      render(<RealTimeCostAndCacheHud />);

      expect(screen.getByText('500 tok')).toBeInTheDocument();
      expect(screen.queryByText(/Cache/)).not.toBeInTheDocument();
      expect(capsule()).not.toHaveClass(HIGHLIGHT);
    });
  });

  describe('prompt cache', () => {
    it('renders token watermark without cache badge when cache threshold is not met', () => {
      showTurns(
        turn({
          prompt_tokens: 500,
          completion_tokens: 100,
          total_tokens: 600,
          cached_tokens: 100, // < 1024 tokens
          net_savings_usd: 0.00002, // < 0.0001 USD
        }),
      );

      render(<RealTimeCostAndCacheHud />);

      expect(screen.getByText('600 tok')).toBeInTheDocument();
      // 低于门限时仅显示灰度比率，不触发绿色高亮微徽章
      expect(screen.getByText('20% Cache')).toBeInTheDocument();
      expect(screen.queryByText(/savedAmount/)).not.toBeInTheDocument();
      expect(capsule()).not.toHaveClass(HIGHLIGHT);
    });

    it('renders highlighted cache badge with savings when threshold is effectively met', () => {
      showTurns(
        turn({
          prompt_tokens: 20000,
          completion_tokens: 800,
          total_tokens: 20800,
          cached_tokens: 16000, // >= 1024 tokens
          net_savings_usd: 0.0432, // >= 0.0001 USD
          cache_hit_rate: 0.8,
          has_effective_cache: true,
        }),
      );

      render(<RealTimeCostAndCacheHud />);

      expect(screen.getByText('20.8K tok')).toBeInTheDocument();
      expect(screen.getByText('80% Cache')).toBeInTheDocument();
      expect(screen.getByText(/^savedAmount:\$0\.043$/)).toBeInTheDocument();
      expect(capsule()).toHaveClass(HIGHLIGHT);
    });

    it('highlights once the cache reads of several replies add up, showing sub-cent savings in four decimals', () => {
      const reply = { prompt_tokens: 3000, total_tokens: 3100, cached_tokens: 600, net_savings_usd: 0.00006 };
      showTurns(turn(reply), turn(reply));

      render(<RealTimeCostAndCacheHud />);

      expect(screen.getByText('20% Cache')).toBeInTheDocument();
      expect(screen.getByText('savedAmount:$0.0001')).toBeInTheDocument();
      expect(capsule()).toHaveClass(HIGHLIGHT);
    });

    it('stays plain when much was read from the cache but next to nothing was saved', () => {
      showTurns(turn({ prompt_tokens: 4000, total_tokens: 4100, cached_tokens: 2000, net_savings_usd: 0.00001 }));

      render(<RealTimeCostAndCacheHud />);

      expect(screen.getByText('50% Cache')).toBeInTheDocument();
      expect(screen.queryByText(/savedAmount/)).not.toBeInTheDocument();
      expect(capsule()).not.toHaveClass(HIGHLIGHT);
    });

    it('trusts the server flag for effective caching even before any saving is reported', () => {
      showTurns(turn({ prompt_tokens: 100, total_tokens: 120, cached_tokens: 50, has_effective_cache: true }));

      render(<RealTimeCostAndCacheHud />);

      expect(screen.getByText('50% Cache')).toBeInTheDocument();
      expect(screen.queryByText(/savedAmount/)).not.toBeInTheDocument();
      expect(capsule()).toHaveClass(HIGHLIGHT);
    });

    it('derives the hit rate from the token totals, not from the 0-1 ratio each reply reports', () => {
      showTurns(turn({ prompt_tokens: 1000, total_tokens: 1100, cached_tokens: 800, cache_hit_rate: 0.8 }));

      render(<RealTimeCostAndCacheHud />);

      expect(screen.getByText('80% Cache')).toBeInTheDocument();
    });
  });

  describe('pricing popover', () => {
    it('looks up the pricing of the selected model', async () => {
      render(<RealTimeCostAndCacheHud />);

      fireEvent.click(capsule());

      expect(await screen.findByText('title')).toBeInTheDocument();
      expect(fetchModelPricing).toHaveBeenLastCalledWith(MODEL);
    });

    it('falls back to the default model while none is selected', async () => {
      useChatStore.setState({ selectedModels: { base: null, vision: null, reasoning: null } });
      render(<RealTimeCostAndCacheHud />);

      fireEvent.click(capsule());

      expect(await screen.findByText('title')).toBeInTheDocument();
      expect(fetchModelPricing).toHaveBeenLastCalledWith('default');
    });
  });
});
