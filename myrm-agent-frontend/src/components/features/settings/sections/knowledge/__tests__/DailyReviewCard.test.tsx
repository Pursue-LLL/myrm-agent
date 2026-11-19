/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const apiRequestMock = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiRequest: apiRequestMock,
}));

import { ApiError } from '@/lib/api';
import DailyReviewCard from '../DailyReviewCard';

const STAGED = {
  success: true,
  raw_path: 'raw/DailyReview/2026-11-19.md',
  enqueued: true,
  skipped: false,
  message: '',
};
const fetchSpy = vi.fn();

async function submitReview(text = 'Shipped the fix', title = 'Thursday') {
  await userEvent.type(screen.getByTestId('daily-review-title-input'), title);
  await userEvent.type(screen.getByTestId('daily-review-text-input'), text);
  await userEvent.click(screen.getByTestId('daily-review-submit-btn'));
}

beforeEach(() => {
  apiRequestMock.mockReset();
  fetchSpy.mockReset();
  vi.stubGlobal('fetch', fetchSpy);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('DailyReviewCard request', () => {
  it('sends the review through the API client, which owns the base URL, and clears the form', async () => {
    apiRequestMock.mockResolvedValue(STAGED);
    render(<DailyReviewCard />);

    await submitReview();

    expect(apiRequestMock).toHaveBeenCalledExactlyOnceWith('/wiki/daily-review', {
      method: 'POST',
      body: JSON.stringify({ text: 'Shipped the fix', title: 'Thursday' }),
      silent: true,
    });
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(await screen.findByTestId('daily-review-result')).toHaveTextContent(STAGED.raw_path);
    expect(screen.getByText('dailyReview.staged')).toBeInTheDocument();
    expect(screen.getByTestId('daily-review-goto-pending')).toHaveAttribute(
      'href',
      '/settings/wiki?wikiTab=pendingEdits',
    );
    expect(screen.getByTestId('daily-review-title-input')).toHaveValue('');
    expect(screen.getByTestId('daily-review-text-input')).toHaveValue('');
  });

  it('reports a same-day duplicate without offering the pending-review link', async () => {
    apiRequestMock.mockResolvedValue({ ...STAGED, enqueued: false, skipped: true });
    render(<DailyReviewCard />);

    await submitReview();

    expect(await screen.findByText('dailyReview.skipped')).toBeInTheDocument();
    expect(screen.queryByTestId('daily-review-goto-pending')).not.toBeInTheDocument();
  });

  it('shows the reason the server gave inline and keeps the text for another try', async () => {
    apiRequestMock.mockRejectedValue(new ApiError('Review blocked by the security policy', 422));
    render(<DailyReviewCard />);

    await submitReview();

    expect(await screen.findByTestId('daily-review-error')).toHaveTextContent('Review blocked by the security policy');
    expect(screen.getByTestId('daily-review-text-input')).toHaveValue('Shipped the fix');
    expect(screen.queryByTestId('daily-review-result')).not.toBeInTheDocument();
  });

  it('shows the localized message instead of the raw transport error', async () => {
    apiRequestMock.mockRejectedValue(new TypeError('Failed to fetch'));
    render(<DailyReviewCard />);

    await submitReview();

    expect(await screen.findByTestId('daily-review-error')).toHaveTextContent('dailyReview.error');
    expect(screen.queryByText('Failed to fetch')).not.toBeInTheDocument();
  });

  it('asks for text first and sends nothing when the review is blank', async () => {
    render(<DailyReviewCard />);

    await userEvent.click(screen.getByTestId('daily-review-submit-btn'));

    expect(screen.getByTestId('daily-review-error')).toHaveTextContent('dailyReview.empty');
    expect(apiRequestMock).not.toHaveBeenCalled();
  });
});
