/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { MockLocale } from '@/test-utils/realIntl';
import type { CronJob, PauseReason } from '@/services/cron.types';

const intl = vi.hoisted(() => ({ locale: 'en' as MockLocale }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));

import CronJobProblemBanner from '../CronJobProblemBanner';

type BannerJob = Pick<CronJob, 'last_error' | 'paused_reason'>;

const LOOP_GUARD_ERROR = 'RUNAWAY_CIRCUIT_BREAKER: pump repeated 5 times';

describe('CronJobProblemBanner', () => {
  afterEach(() => {
    cleanup();
    intl.locale = 'en';
  });

  it('is absent while the job has neither a reason nor an error', () => {
    const { container } = render(<CronJobProblemBanner job={{}} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('shows the last error alone for a job nothing paused', () => {
    render(<CronJobProblemBanner job={{ last_error: 'pump is dry' }} />);

    expect(screen.getByText('Last Error: pump is dry')).toBeInTheDocument();
  });

  it.each<[PauseReason, string, string]>([
    ['run_failures', 'It kept failing, so it was paused automatically.', '多次执行失败，已自动暂停。'],
    ['schedule_error', 'Its schedule is invalid, so it was paused automatically.', '执行计划无效，已自动暂停。'],
  ])('says why a job was paused for %s, in both languages, above the error it left', (reason, english, chinese) => {
    const job: BannerJob = { paused_reason: reason, last_error: 'pump is dry' };

    render(<CronJobProblemBanner job={job} />);
    expect(screen.getByText(english)).toBeInTheDocument();
    expect(screen.getByText('Last Error: pump is dry')).toBeInTheDocument();

    cleanup();
    intl.locale = 'zh';
    render(<CronJobProblemBanner job={job} />);
    expect(screen.getByText(chinese)).toBeInTheDocument();
    expect(screen.getByText('上次错误: pump is dry')).toBeInTheDocument();
  });

  it.each<[MockLocale, string]>([
    ['en', 'Runaway loop detected: execution halted and retries blocked to protect compute budget'],
    ['zh', '智能识别到死循环，已主动熔断并阻止重试以保护算力消耗'],
  ])('words a loop-guard pause in %s without the guard\'s own error text', (locale, sentence) => {
    intl.locale = locale;

    render(<CronJobProblemBanner job={{ paused_reason: 'circuit_break', last_error: LOOP_GUARD_ERROR }} />);

    expect(screen.getByText(sentence)).toBeInTheDocument();
    expect(screen.queryByText(new RegExp(LOOP_GUARD_ERROR))).not.toBeInTheDocument();
  });
});
