import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ReasoningTokenIntegrityHUD } from '../ReasoningTokenIntegrityHUD';
import type {
  InvariantCheckResult,
  NormalizedTokenUsageSnapshot,
  ProviderPolicyItem,
} from '../reasoningSemanticsTypes';

describe('ReasoningTokenIntegrityHUD', () => {
  const mockSnapshot: NormalizedTokenUsageSnapshot = {
    prompt_tokens: 1200,
    completion_tokens: 3500,
    reasoning_tokens: 2000,
    visible_content_tokens: 1500,
    total_tokens: 4700,
    cost_usd: 0.0561,
    is_zero_double_counted: true,
    raw_provider: 'openai/o3-mini',
    policy_applied: 'INCLUDED_IN_COMPLETION',
    normalized_at: '2026-10-12T00:00:00Z',
  };

  const mockPolicies: ProviderPolicyItem[] = [
    {
      provider_keyword: 'openai',
      policy: 'INCLUDED_IN_COMPLETION',
      description: 'OpenAI 官方规范 (o1/o3/gpt-4o): completion_tokens 包含 reasoning_tokens',
    },
    {
      provider_keyword: 'anthropic',
      policy: 'INCLUDED_IN_COMPLETION',
      description: 'Anthropic 规范 (Claude 3.7 Sonnet Thinking): output_tokens 包含 thinking_tokens',
    },
  ];

  it('renders honest subordination hierarchy and invariant formula without double-counting', () => {
    render(
      <ReasoningTokenIntegrityHUD
        snapshot={mockSnapshot}
        policies={mockPolicies}
      />
    );

    // Title & Badge
    expect(screen.getByText('推理 Token 计费语义契约与重复计数守卫')).toBeInTheDocument();
    expect(screen.getByText('Zero Double-Counting Verified')).toBeInTheDocument();

    // Provider & Policy tags
    expect(screen.getByText('openai/o3-mini')).toBeInTheDocument();
    expect(screen.getAllByText('INCLUDED_IN_COMPLETION').length).toBeGreaterThanOrEqual(1);

    // Token Hierarchy (Total, Prompt, Completion, Reasoning, Visible)
    expect(screen.getByText('4,700 Tokens')).toBeInTheDocument();
    expect(screen.getByText('1,200')).toBeInTheDocument();
    expect(screen.getByText('3,500')).toBeInTheDocument();
    expect(screen.getByText('2,000 Tokens')).toBeInTheDocument();
    expect(screen.getByText('1,500 Tokens')).toBeInTheDocument();

    // Formula text
    expect(screen.getByText('公式不变量:')).toBeInTheDocument();
    expect(screen.getByText(/Total \(4700\)/)).toBeInTheDocument();
    expect(screen.getByText(/Prompt \(1200\)/)).toBeInTheDocument();
    expect(screen.getByText(/Completion \(3500\)/)).toBeInTheDocument();

    // Policies
    expect(screen.getByText('openai')).toBeInTheDocument();
    expect(screen.getByText('anthropic')).toBeInTheDocument();
  });

  it('renders warning banner when upstream double counting violation is detected and auto-healed', () => {
    const mockCheckResult: InvariantCheckResult = {
      is_valid: false,
      violation_type: 'DOUBLE_COUNTING_TOTAL',
      diagnostic_warning: '检测到严重重复计数漏洞: 上报 total (6700) 包含了 prompt + completion + reasoning。',
      corrected_snapshot: mockSnapshot,
    };

    render(
      <ReasoningTokenIntegrityHUD
        snapshot={mockSnapshot}
        checkResult={mockCheckResult}
      />
    );

    expect(screen.getByText(/上游重复计数漏洞警示 \(已启动运行时自愈纠偏\)/)).toBeInTheDocument();
    expect(screen.getByText(/检测到严重重复计数漏洞/)).toBeInTheDocument();
  });

  it('handles verify invariant and policy refresh button callbacks', () => {
    const onVerify = vi.fn();
    const onRefresh = vi.fn();

    render(
      <ReasoningTokenIntegrityHUD
        snapshot={mockSnapshot}
        policies={mockPolicies}
        onVerifyInvariant={onVerify}
        onRefreshPolicies={onRefresh}
      />
    );

    const verifyBtn = screen.getByRole('button', { name: /验证不变量契约/ });
    fireEvent.click(verifyBtn);
    expect(onVerify).toHaveBeenCalledTimes(1);

    const refreshBtn = screen.getByRole('button', { name: '刷新策略' });
    fireEvent.click(refreshBtn);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});
