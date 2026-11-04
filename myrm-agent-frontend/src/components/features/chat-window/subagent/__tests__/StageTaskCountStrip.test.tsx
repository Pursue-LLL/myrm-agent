/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { StageTaskCountSummary } from '@/lib/utils/subagent/stageTaskCount';
import type { MockLocale } from '@/test-utils/realIntl';

const { intl } = vi.hoisted(() => ({ intl: { locale: 'en' as MockLocale } }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));

import { StageTaskCountStrip } from '../StageTaskCountStrip';

const summary: StageTaskCountSummary = {
  stages: [
    {
      id: 'verify',
      category: 'verify',
      name: 'Verify',
      completed: 0,
      total: 2,
      running: 0,
      failed: 0,
      waitingOnStage: 'Build',
      isBlocked: true,
      isComplete: false,
    },
  ],
  totalTasks: 2,
  totalCompleted: 0,
  hasBlockers: true,
};

describe('StageTaskCountStrip', () => {
  beforeEach(() => {
    intl.locale = 'en';
  });

  it('names the stage a blocked stage is waiting on in English', () => {
    render(<StageTaskCountStrip summary={summary} />);

    expect(screen.getByText('(waiting on Build)')).toBeInTheDocument();
  });

  it('names the stage a blocked stage is waiting on in Chinese', () => {
    intl.locale = 'zh';
    render(<StageTaskCountStrip summary={summary} />);

    expect(screen.getByText('（等待 Build）')).toBeInTheDocument();
  });
});
