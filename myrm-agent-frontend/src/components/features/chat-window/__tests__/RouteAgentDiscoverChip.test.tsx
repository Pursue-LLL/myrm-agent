'use client';

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import RouteAgentDiscoverChip from '../RouteAgentDiscoverChip';

const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

const translations: Record<string, string> = {
  title: '智能专职派发与能力画像',
  subtitle: '声明式匹配架构师、审查员、调研员专职智能体，防盲目误派护栏护航',
  guardrailBadge: '防误派防御',
  action: '查看能力目录',
  dismiss: '稍后再看',
  'specialists.coder': '代码实现',
  'specialists.reviewer': '代码审查',
  'specialists.researcher': '网络调研',
  'specialists.architect': '架构设计',
  'specialists.auditor': '安全合规',
};
const stableT = (key: string) => translations[key] ?? key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

let mockStore: Record<string, string> = {};
const mockSessionStorage = {
  getItem: vi.fn((key: string) => mockStore[key] ?? null),
  setItem: vi.fn((key: string, value: string) => {
    mockStore[key] = String(value);
  }),
  removeItem: vi.fn((key: string) => {
    delete mockStore[key];
  }),
  clear: vi.fn(() => {
    mockStore = {};
  }),
};

if (typeof globalThis.sessionStorage === 'undefined') {
  Object.defineProperty(globalThis, 'sessionStorage', {
    value: mockSessionStorage,
    writable: true,
  });
}

describe('RouteAgentDiscoverChip', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it('renders correctly when not dismissed', () => {
    render(<RouteAgentDiscoverChip />);
    expect(screen.getByTestId('route-agent-discover-chip')).toBeInTheDocument();
    expect(screen.getByText('智能专职派发与能力画像')).toBeInTheDocument();
    expect(screen.getByText('防误派防御')).toBeInTheDocument();
    expect(screen.getByText('代码实现')).toBeInTheDocument();
    expect(screen.getByText('代码审查')).toBeInTheDocument();
    expect(screen.getByText('网络调研')).toBeInTheDocument();
    expect(screen.getByText('架构设计')).toBeInTheDocument();
    expect(screen.getByText('安全合规')).toBeInTheDocument();
  });

  it('navigates to fleet capabilities catalog on card click', () => {
    render(<RouteAgentDiscoverChip />);
    const chip = screen.getByTestId('route-agent-discover-chip');
    fireEvent.click(chip);
    expect(mockPush).toHaveBeenCalledWith('/agents?view=fleet&tab=capabilities');
  });

  it('invokes onSelectAgent callback when specialist badge is clicked', () => {
    const handleSelect = vi.fn();
    render(<RouteAgentDiscoverChip onSelectAgent={handleSelect} />);
    const coderBadge = screen.getByTestId('badge-coder');
    fireEvent.click(coderBadge);

    expect(handleSelect).toHaveBeenCalledWith('coder');
    expect(mockPush).not.toHaveBeenCalled();
  });

  it('navigates with focus query when badge is clicked without custom handler', () => {
    render(<RouteAgentDiscoverChip />);
    const researcherBadge = screen.getByTestId('badge-researcher');
    fireEvent.click(researcherBadge);

    expect(mockPush).toHaveBeenCalledWith('/agents?view=fleet&focus=researcher');
  });

  it('dismisses when close button is clicked and stores in sessionStorage', () => {
    render(<RouteAgentDiscoverChip />);
    const dismissBtn = screen.getByRole('button', { name: '稍后再看' });
    fireEvent.click(dismissBtn);

    expect(screen.queryByTestId('route-agent-discover-chip')).not.toBeInTheDocument();
    expect(sessionStorage.getItem('myrm_route_agent_discover_chip_dismissed')).toBe('true');
  });

  it('does not render if previously dismissed in sessionStorage', () => {
    sessionStorage.setItem('myrm_route_agent_discover_chip_dismissed', 'true');
    render(<RouteAgentDiscoverChip />);
    expect(screen.queryByTestId('route-agent-discover-chip')).not.toBeInTheDocument();
  });
});
