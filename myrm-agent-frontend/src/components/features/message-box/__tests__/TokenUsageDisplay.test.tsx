import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { TokenUsage, TokenEconomicsSnapshot, ContextBudget } from '@/store/chat/types';

const mockIsLocalMode = vi.fn(() => true);
const mockEnableCostEstimation = vi.fn(() => true);

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: () => mockIsLocalMode(),
}));

vi.mock('@/store/useConfigStore', () => ({
  default: (selector: (s: { enableCostEstimation: boolean }) => boolean) =>
    selector({ enableCostEstimation: mockEnableCostEstimation() }),
}));

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      setActiveSessionAnalyticsId: vi.fn(),
      setActiveSessionAnalyticsMessageId: vi.fn(),
    }),
}));

vi.mock('@/services/statistics', () => ({
  getSessionAnalytics: vi.fn().mockResolvedValue(null),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/components/primitives/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div data-testid="tooltip-content">{children}</div>,
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import TokenUsageDisplay from '../TokenUsageDisplay';

function makeUsage(overrides: Partial<TokenUsage> = {}): TokenUsage {
  return {
    prompt_tokens: 1500,
    completion_tokens: 500,
    total_tokens: 2000,
    ...overrides,
  };
}

function makeTokenEconomics(overrides: Partial<TokenEconomicsSnapshot> = {}): TokenEconomicsSnapshot {
  return {
    usage: makeUsage(),
    call_count: 1,
    total_cost_usd: 0.05,
    cost_status: 'actual',
    error_count: 0,
    latency: {
      avg_ms: 800,
      p95_ms: 1200,
      min_ms: 600,
      max_ms: 1500,
      avg_ttft_ms: 200,
      p95_ttft_ms: 350,
      avg_tokens_per_second: 45,
    },
    ...overrides,
  };
}

function makeBudget(overrides: Partial<ContextBudget> = {}): ContextBudget {
  return {
    current_tokens: 4000,
    max_context_tokens: 128000,
    usage_percent: 3.1,
    health_status: 'healthy',
    ...overrides,
  };
}

describe('TokenUsageDisplay', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsLocalMode.mockReturnValue(true);
    mockEnableCostEstimation.mockReturnValue(true);
  });

  // --- 渲染守卫 ---

  it('renders nothing when not in local mode', () => {
    mockIsLocalMode.mockReturnValue(false);
    const { container } = render(<TokenUsageDisplay usage={makeUsage()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when cost estimation is disabled', () => {
    mockEnableCostEstimation.mockReturnValue(false);
    const { container } = render(<TokenUsageDisplay usage={makeUsage()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when usage has zero total tokens', () => {
    const { container } = render(
      <TokenUsageDisplay usage={makeUsage({ total_tokens: 0, prompt_tokens: 0, completion_tokens: 0 })} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when usage is undefined', () => {
    const { container } = render(<TokenUsageDisplay usage={undefined as unknown as TokenUsage} />);
    expect(container).toBeEmptyDOMElement();
  });

  // --- 基本渲染 ---

  it('renders trigger button with formatted token count', () => {
    render(<TokenUsageDisplay usage={makeUsage({ total_tokens: 2000 })} />);
    const elements = screen.getAllByText('2.0k');
    expect(elements.length).toBeGreaterThanOrEqual(1);
  });

  it('formats large token counts with M suffix', () => {
    render(<TokenUsageDisplay usage={makeUsage({ total_tokens: 1500000, prompt_tokens: 1000000, completion_tokens: 500000 })} />);
    const elements = screen.getAllByText('1.5M');
    expect(elements.length).toBeGreaterThanOrEqual(1);
  });

  it('displays raw number for small token counts', () => {
    render(<TokenUsageDisplay usage={makeUsage({ total_tokens: 500, prompt_tokens: 300, completion_tokens: 200 })} />);
    const elements = screen.getAllByText('500');
    expect(elements.length).toBeGreaterThanOrEqual(1);
  });

  // --- 模型信息展示 (SM-02 核心验证) ---

  it('displays model name when provided', () => {
    render(<TokenUsageDisplay usage={makeUsage()} modelName="openai/gpt-4o" />);
    expect(screen.getByText('gpt-4o')).toBeInTheDocument();
  });

  it('formats model name by extracting after last slash', () => {
    render(<TokenUsageDisplay usage={makeUsage()} modelName="anthropic/claude-sonnet-4-20250514" />);
    expect(screen.getByText('claude-sonnet-4-20250514')).toBeInTheDocument();
  });

  it('displays model name without slash as-is', () => {
    render(<TokenUsageDisplay usage={makeUsage()} modelName="gpt-4o-mini" />);
    expect(screen.getByText('gpt-4o-mini')).toBeInTheDocument();
  });

  it('displays routing tier badge for simple', () => {
    render(<TokenUsageDisplay usage={makeUsage()} modelName="test" routingTier="simple" />);
    expect(screen.getByText('routingSimple')).toBeInTheDocument();
  });

  it('displays routing tier badge for reasoning', () => {
    render(<TokenUsageDisplay usage={makeUsage()} modelName="test" routingTier="reasoning" />);
    expect(screen.getByText('routingReasoning')).toBeInTheDocument();
  });

  it('displays routing tier badge for standard', () => {
    render(<TokenUsageDisplay usage={makeUsage()} modelName="test" routingTier="standard" />);
    expect(screen.getByText('routingStandard')).toBeInTheDocument();
  });

  // --- 模型兼容层 ---

  it('displays model tier when provided', () => {
    render(<TokenUsageDisplay usage={makeUsage()} modelTier="weak" />);
    expect(screen.getByText('compatMode')).toBeInTheDocument();
  });

  // --- 隐私级别 ---

  it('does not display privacy section for s1 (public)', () => {
    render(<TokenUsageDisplay usage={makeUsage()} privacyLevel="s1" />);
    expect(screen.queryByText('privacyS2')).not.toBeInTheDocument();
    expect(screen.queryByText('privacyS3')).not.toBeInTheDocument();
  });

  it('displays privacy level s2', () => {
    render(<TokenUsageDisplay usage={makeUsage()} privacyLevel="s2" />);
    expect(screen.getByText('privacyS2')).toBeInTheDocument();
  });

  it('displays privacy level s3', () => {
    render(<TokenUsageDisplay usage={makeUsage()} privacyLevel="s3" />);
    expect(screen.getByText('privacyS3')).toBeInTheDocument();
  });

  it('displays privacy route local', () => {
    render(<TokenUsageDisplay usage={makeUsage()} privacyRoute="local" />);
    expect(screen.getByText('privacyRouteLocal')).toBeInTheDocument();
  });

  it('displays privacy route cloud', () => {
    render(<TokenUsageDisplay usage={makeUsage()} privacyRoute="cloud" />);
    expect(screen.getByText('privacyRouteCloud')).toBeInTheDocument();
  });

  // --- 缓存 Token ---

  it('displays cached tokens with savings percentage', () => {
    render(<TokenUsageDisplay usage={makeUsage({ cached_tokens: 1000 })} />);
    expect(screen.getByText('1,000')).toBeInTheDocument();
    expect(screen.getByText('-67%')).toBeInTheDocument();
  });

  // --- 推理 Token ---

  it('displays reasoning tokens when present', () => {
    render(<TokenUsageDisplay usage={makeUsage({ reasoning_tokens: 300 })} />);
    expect(screen.getByText('300')).toBeInTheDocument();
    expect(screen.getByText('reasoningTokens')).toBeInTheDocument();
  });

  // --- 引用 Token ---

  it('displays citation tokens when present', () => {
    render(<TokenUsageDisplay usage={makeUsage({ citation_tokens: 200 })} />);
    expect(screen.getByText('200')).toBeInTheDocument();
    expect(screen.getByText('citationTokens')).toBeInTheDocument();
  });

  // --- 费用 ---

  it('displays cost when provided', () => {
    render(<TokenUsageDisplay usage={makeUsage()} costUsd={0.05} costStatus="actual" />);
    expect(screen.getByText('$0.05')).toBeInTheDocument();
    expect(screen.getByText('costActual')).toBeInTheDocument();
  });

  it('displays estimated cost badge', () => {
    render(<TokenUsageDisplay usage={makeUsage()} costUsd={0.001} costStatus="estimated" />);
    expect(screen.getByText('$0.0010')).toBeInTheDocument();
    expect(screen.getByText('costEstimated')).toBeInTheDocument();
  });

  it('formats very small costs with less-than prefix', () => {
    render(<TokenUsageDisplay usage={makeUsage()} costUsd={0.00001} />);
    expect(screen.getByText('<$0.0001')).toBeInTheDocument();
  });

  // --- 上下文预算 ---

  it('displays context budget ring with percentage', () => {
    render(<TokenUsageDisplay usage={makeUsage()} contextBudget={makeBudget()} />);
    expect(screen.getByText('3%')).toBeInTheDocument();
  });

  it('displays warning status for context budget', () => {
    render(
      <TokenUsageDisplay usage={makeUsage()} contextBudget={makeBudget({ health_status: 'warning', usage_percent: 75 })} />,
    );
    expect(screen.getByText('75%')).toBeInTheDocument();
    expect(screen.getByText('contextWarning')).toBeInTheDocument();
  });

  it('displays critical status for context budget', () => {
    render(
      <TokenUsageDisplay usage={makeUsage()} contextBudget={makeBudget({ health_status: 'critical', usage_percent: 95 })} />,
    );
    expect(screen.getByText('95%')).toBeInTheDocument();
    expect(screen.getByText('contextCritical')).toBeInTheDocument();
  });

  // --- 缓存失效归因 ---

  it('displays cache break reason when no cached tokens', () => {
    render(
      <TokenUsageDisplay
        usage={makeUsage({ cached_tokens: 0 })}
        cacheBreakReason="System prompt changed"
      />,
    );
    expect(screen.getAllByText('System prompt changed').length).toBeGreaterThanOrEqual(1);
  });

  // --- 多模型分解 ---

  it('displays model breakdown when present', () => {
    const economics = makeTokenEconomics({
      model_breakdown: {
        'openai/gpt-4o': { prompt_tokens: 1000, completion_tokens: 400, total_tokens: 1400, cost_usd: 0.03 },
        'anthropic/claude-sonnet-4': { prompt_tokens: 500, completion_tokens: 100, total_tokens: 600, cost_usd: 0.02 },
      },
    });
    render(<TokenUsageDisplay usage={makeUsage()} tokenEconomics={economics} />);
    expect(screen.getByText('modelBreakdown')).toBeInTheDocument();
    expect(screen.getAllByText('gpt-4o').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('claude-sonnet-4')).toBeInTheDocument();
  });

  // --- 工具分解 ---

  it('displays tool breakdown when present', () => {
    const economics = makeTokenEconomics({
      tool_breakdown: {
        'file_read': { prompt_tokens: 300, completion_tokens: 50, total_tokens: 350, cost_usd: 0.005 },
      },
    });
    render(<TokenUsageDisplay usage={makeUsage()} tokenEconomics={economics} />);
    expect(screen.getByText('file_read')).toBeInTheDocument();
  });

  // --- 组合场景 ---

  it('renders complete model transparency info simultaneously', () => {
    render(
      <TokenUsageDisplay
        usage={makeUsage({ cached_tokens: 500, reasoning_tokens: 200 })}
        modelName="openai/gpt-4o"
        routingTier="reasoning"
        privacyLevel="s2"
        privacyRoute="cloud"
        costUsd={0.05}
        costStatus="actual"
        contextBudget={makeBudget()}
      />,
    );
    expect(screen.getByText('gpt-4o')).toBeInTheDocument();
    expect(screen.getByText('routingReasoning')).toBeInTheDocument();
    expect(screen.getByText('privacyS2')).toBeInTheDocument();
    expect(screen.getByText('$0.05')).toBeInTheDocument();
    expect(screen.getByText('3%')).toBeInTheDocument();
  });
});
