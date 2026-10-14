import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { CronJob } from '@/services/cron.types';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/cron', () => ({
  updateCronJob: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { TriggerEditor } from '../CronTriggerEditor';

function jobWithEventTrigger(): CronJob {
  const job: Partial<CronJob> = {
    id: 'job-1',
    triggers: {
      webhooks: [],
      events: [{ pattern: 'server down', channel: 'feishu' }],
      system_events: [],
      polls: [],
      streams: [],
    },
  };
  return job as CronJob;
}

describe('TriggerEditor event triggers', () => {
  it('tells the owner which messages can fire an event trigger', () => {
    render(<TriggerEditor job={jobWithEventTrigger()} onUpdated={vi.fn()} />);

    expect(screen.getByText('triggerEventLabel')).toBeInTheDocument();
    expect(screen.getByText('triggerEventDesc')).toBeInTheDocument();
  });
});
