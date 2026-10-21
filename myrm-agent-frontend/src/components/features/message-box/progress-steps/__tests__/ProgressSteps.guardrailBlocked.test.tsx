import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import en from '../../../../../../locales/en.json';
import zh from '../../../../../../locales/zh.json';

import ProgressSteps from '../ProgressSteps';
import type { ProgressItem } from '@/store/chat/types';

type ProgressStepsLocale = {
  errorCategories: Record<string, string>;
};

function getGuardrailBlockedLabel(bundle: typeof zh): string {
  const progressSteps = bundle.progressSteps as ProgressStepsLocale;
  const label = progressSteps.errorCategories.guardrail_blocked;
  if (!label) {
    throw new Error('progressSteps.errorCategories.guardrail_blocked missing from locale bundle');
  }
  return label;
}

vi.mock('next-intl', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const zhBundle = require('../../../../../../locales/zh.json') as typeof zh;
  const guardrailLabel = getGuardrailBlockedLabel(zhBundle);
  return {
    useTranslations: (namespace: string) => (key: string) => {
      if (namespace === 'progressSteps' && key === 'errorCategories.guardrail_blocked') {
        return guardrailLabel;
      }
      return key;
    },
  };
});

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => ({ sendMessage: vi.fn() }),
  },
}));

describe('ProgressSteps guardrail_blocked badge', () => {
  it('keeps guardrail_blocked labels in zh and en locale files', () => {
    const zhLabel = getGuardrailBlockedLabel(zh);
    const enLabel = getGuardrailBlockedLabel(en);
    expect(zhLabel).toBe('安全拦截');
    expect(enLabel).toBe('Safety Blocked');
    expect(zhLabel).not.toBe(enLabel);
  });

  it('renders the safety-blocked badge when error_category is guardrail_blocked', () => {
    const expectedLabel = getGuardrailBlockedLabel(zh);
    const steps: ProgressItem[] = [
      {
        step_key: 'executing_code',
        tool_name: 'bash_code_execute_tool',
        status: 'error',
        error: true,
        error_category: 'guardrail_blocked',
      },
    ];

    render(<ProgressSteps messageId="msg-guardrail" steps={steps} loading={false} />);

    expect(screen.getByText(expectedLabel)).toBeInTheDocument();
  });
});
