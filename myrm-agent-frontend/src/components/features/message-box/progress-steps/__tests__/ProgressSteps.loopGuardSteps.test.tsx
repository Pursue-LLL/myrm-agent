/** @vitest-environment jsdom */
/**
 * The loop guard steps reach the user as readable rows: the catalog wording, not a raw key or an empty row.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import en from '../../../../../../locales/en.json';
import ProgressSteps from '../ProgressSteps';
import type { ProgressItem } from '@/store/chat/types';

const progressSteps: Record<string, unknown> = en.progressSteps;
const catalogT = (key: string) => (typeof progressSteps[key] === 'string' ? progressSteps[key] : key);

vi.mock('next-intl', () => ({
  useTranslations: () => catalogT,
  useLocale: () => 'en',
}));

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: unknown) => unknown) => selector({ sendMessage: vi.fn(), messages: [] }),
}));

const loopGuardSteps: Array<ProgressItem & { wording: string }> = [
  { step_key: 'tool_stuck_paused', items: [], status: 'error', wording: en.progressSteps.tool_stuck_paused },
  { step_key: 'loop_guard_break', items: [], status: 'error', wording: en.progressSteps.loop_guard_break },
];

describe('ProgressSteps loop guard rows', () => {
  it.each(loopGuardSteps)('lists $step_key with its catalog wording once the task list is expanded', async (item) => {
    const { wording, ...step } = item;
    render(<ProgressSteps messageId={`msg-${step.step_key}`} steps={[step]} loading={false} />);

    await userEvent.click(screen.getByTestId('progress-steps-toggle'));

    expect(screen.getAllByText(wording).length).toBeGreaterThan(0);
    expect(screen.queryByText(step.step_key)).toBeNull();
  });
});
