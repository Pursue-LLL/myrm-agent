import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

const mockToastSuccess = vi.fn();

vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => mockToastSuccess(...args),
    error: vi.fn(),
  },
}));

const stableT = (key: string, values?: Record<string, string>) => {
  const translations: Record<string, string> = {
    title: 'Role Chain Presets',
    badge: 'Role Chain',
    chainAssembled: `Assembled role chain: ${values?.name || ''}`,
    'chains.implement_review_fix.name': 'Implement ➔ Review ➔ Fix (Review-Loop)',
    'chains.implement_review_fix.desc': 'Implementation followed by 3-lens review and fix iterations (max 3 rounds)',
    'chains.implement_review_fix.prompt':
      '[Role Chain: Implement ➔ Review ➔ Fix (Max 3 Rounds)] Please sequentially orchestrate subagents:',
    'chains.clarify_scout_worker.name': 'Clarify ➔ Scout ➔ Worker',
    'chains.clarify_scout_worker.desc': 'Clarify requirements, scout codebase, deliver output',
    'chains.clarify_scout_worker.prompt':
      '[Role Chain: Clarify ➔ Scout ➔ Worker] Please first delegate to Strategic Advisor:',
    'chains.watchdog_guard.name': 'Watchdog Guard ➔ Adversarial Audit',
    'chains.watchdog_guard.desc': 'PRE_TOOL_USE safety boundary check and adversarial audit',
    'chains.watchdog_guard.prompt': '[Role Chain: Watchdog Guard ➔ Adversarial Audit] Please gate tool execution:',
    'chains.editorial_publish.name': 'Editorial ➔ Deep Draft ➔ Final Proofread',
    'chains.editorial_publish.desc': 'Editorial guidelines, deep drafting and fact-checking',
    'chains.editorial_publish.prompt': '[Role Chain: Editorial ➔ Deep Draft ➔ Final Proofread] Please draft content:',
  };
  return translations[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockSetInputMessage = vi.fn();
let mockCurrentInput = '';

vi.mock('@/store/useChatStore', () => {
  const store = (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      setInputMessage: mockSetInputMessage,
      inputMessage: mockCurrentInput,
    });
  store.getState = () => ({
    setInputMessage: mockSetInputMessage,
    inputMessage: mockCurrentInput,
  });
  return { default: store };
});

import SubagentRoleChainPresetChips from '../SubagentRoleChainPresetChips';

describe('SubagentRoleChainPresetChips', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCurrentInput = '';
  });

  it('renders all 4 golden role chain preset chips', () => {
    render(<SubagentRoleChainPresetChips />);

    expect(screen.getByTestId('subagent-role-chain-preset-chips')).toBeInTheDocument();
    expect(screen.getByTestId('role-chain-chip-implement_review_fix')).toBeInTheDocument();
    expect(screen.getByTestId('role-chain-chip-clarify_scout_worker')).toBeInTheDocument();
    expect(screen.getByTestId('role-chain-chip-watchdog_guard')).toBeInTheDocument();
    expect(screen.getByTestId('role-chain-chip-editorial_publish')).toBeInTheDocument();

    expect(screen.getByText('Implement ➔ Review ➔ Fix (Review-Loop)')).toBeInTheDocument();
    expect(screen.getByText('Loop max 3')).toBeInTheDocument();
    expect(screen.getByText('Art 55 Guard')).toBeInTheDocument();
  });

  it('applies implement-review-fix chain and sets structured orchestration prompt', () => {
    const onSelectMock = vi.fn();
    render(<SubagentRoleChainPresetChips onSelectChain={onSelectMock} />);

    const chip = screen.getByTestId('role-chain-chip-implement_review_fix');
    fireEvent.click(chip);

    expect(mockSetInputMessage).toHaveBeenCalledWith(
      '[Role Chain: Implement ➔ Review ➔ Fix (Max 3 Rounds)] Please sequentially orchestrate subagents:',
    );
    expect(mockToastSuccess).toHaveBeenCalledWith('Assembled role chain: Implement ➔ Review ➔ Fix (Review-Loop)');
    expect(onSelectMock).toHaveBeenCalledWith('implement_review_fix');
  });

  it('prepends chain protocol when composer already has existing text', () => {
    mockCurrentInput = 'Fix null pointer in auth.ts';
    render(<SubagentRoleChainPresetChips />);

    const chip = screen.getByTestId('role-chain-chip-watchdog_guard');
    fireEvent.click(chip);

    expect(mockSetInputMessage).toHaveBeenCalledWith(
      '[Role Chain: Watchdog Guard ➔ Adversarial Audit] Please gate tool execution:\nFix null pointer in auth.ts',
    );
  });
});
