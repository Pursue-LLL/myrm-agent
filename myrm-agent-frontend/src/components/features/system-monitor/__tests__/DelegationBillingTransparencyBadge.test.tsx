/**
 * [INPUT]: DelegationBillingTransparencyBadge component, mock DelegationUsageBadgeData.
 * [OUTPUT]: Vitest test suite verifying subscription zero-billed capsule, API metered badge, source attribution, and detail expansion.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/__tests__/DelegationBillingTransparencyBadge.test.tsx
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { DelegationBillingTransparencyBadge } from '../DelegationBillingTransparencyBadge';
import { DelegationUsageBadgeData } from '../delegationBillingTypes';

describe('DelegationBillingTransparencyBadge Component', () => {
  it('renders subscription mode with zero billable badge, savings, and source tag', async () => {
    const mockUsage: DelegationUsageBadgeData = {
      prompt_tokens: 1000,
      completion_tokens: 500,
      total_tokens: 1500,
      auth_mode: 'subscription',
      billable: false,
      source: 'delegate:claude',
      estimated_savings_usd: 0.0105,
    };

    render(<DelegationBillingTransparencyBadge usage={mockUsage} />);

    expect(screen.getByTestId('delegation-billing-badge')).toBeInTheDocument();
    expect(screen.getByText(/订阅额度 1,500 tokens/)).toBeInTheDocument();
    expect(screen.getByText('不计费')).toBeInTheDocument();
    expect(screen.getByText('(已省 $0.0105)')).toBeInTheDocument();
    expect(screen.getByText('claude')).toBeInTheDocument();

    // Click to expand details
    const badgeBtn = screen.getByRole('button', { name: /Subscription delegation badge/i });
    await act(async () => {
      fireEvent.click(badgeBtn);
    });

    expect(screen.getByText(/个人订阅专属额度 \(无 API 账单\)/)).toBeInTheDocument();
    expect(screen.getByText('1,000 / 500')).toBeInTheDocument();
    expect(screen.getByText('$0.0105')).toBeInTheDocument();
  });

  it('renders API key metered mode with dollar cost and source backend tag', async () => {
    const mockUsage: DelegationUsageBadgeData = {
      prompt_tokens: 2000,
      completion_tokens: 1000,
      total_tokens: 3000,
      auth_mode: 'api_key',
      billable: true,
      source: 'invoke_acp:codex',
      cost_usd: 0.021,
    };

    render(<DelegationBillingTransparencyBadge usage={mockUsage} />);

    expect(screen.getByText('API 计费')).toBeInTheDocument();
    expect(screen.getByText('$0.0210')).toBeInTheDocument();
    expect(screen.getByText('3,000 tokens')).toBeInTheDocument();
    expect(screen.getByText('codex')).toBeInTheDocument();

    // Click to expand details
    const badgeBtn = screen.getByRole('button', { name: /API key delegation badge/i });
    await act(async () => {
      fireEvent.click(badgeBtn);
    });

    expect(screen.getByText(/团队 API 计费密钥 \(扣减余额\)/)).toBeInTheDocument();
    expect(screen.getByText('2,000 / 1,000')).toBeInTheDocument();
  });

  it('handles fallback when not a delegation event', () => {
    const mockEmpty: DelegationUsageBadgeData = {
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
    };

    const { container } = render(<DelegationBillingTransparencyBadge usage={mockEmpty} />);
    expect(container.firstChild).toBeNull();
  });
});
