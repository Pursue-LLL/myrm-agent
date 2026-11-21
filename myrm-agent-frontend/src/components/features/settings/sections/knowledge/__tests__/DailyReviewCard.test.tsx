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
import { WikiAgentScopeProvider } from '../WikiAgentScopeContext';

// The server answers with more than the card reads; none of the extra fields may reach the UI.
const STAGED = {
  success: true,
  raw_path: 'raw/DailyReview/2026-11-19.md',
  enqueued: true,
  skipped: false,
  message: '',
};
const fetchSpy = vi.fn();

function Card({ agentScopeId = null }: { agentScopeId?: string | null }) {
  return (
    <WikiAgentScopeProvider agentScopeId={agentScopeId} scopeRevision={0} scopeLabel="scope">
      <DailyReviewCard />
    </WikiAgentScopeProvider>
  );
}

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
    render(<Card />);

    await submitReview();

    expect(apiRequestMock).toHaveBeenCalledExactlyOnceWith('/wiki/daily-review', {
      method: 'POST',
      body: JSON.stringify({ text: 'Shipped the fix', title: 'Thursday' }),
      silent: true,
    });
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(await screen.findByTestId('daily-review-result')).toBeInTheDocument();
    expect(screen.getByText('dailyReview.staged')).toBeInTheDocument();
    expect(screen.getByTestId('daily-review-goto-pending')).toHaveAttribute(
      'href',
      '/settings/wiki?wikiTab=pendingEdits',
    );
    expect(screen.getByTestId('daily-review-title-input')).toHaveValue('');
    expect(screen.getByTestId('daily-review-text-input')).toHaveValue('');
  });

  it('never shows the internal vault path of the stored review', async () => {
    apiRequestMock.mockResolvedValue(STAGED);
    render(<Card />);

    await submitReview();

    expect(await screen.findByTestId('daily-review-result')).not.toHaveTextContent(STAGED.raw_path);
  });

  it('reports a same-day duplicate without offering the pending-review link', async () => {
    apiRequestMock.mockResolvedValue({ ...STAGED, enqueued: false, skipped: true });
    render(<Card />);

    await submitReview();

    expect(await screen.findByText('dailyReview.skipped')).toBeInTheDocument();
    expect(screen.queryByTestId('daily-review-goto-pending')).not.toBeInTheDocument();
  });

  it('asks for text first and sends nothing when the review is blank', async () => {
    render(<Card />);

    await userEvent.click(screen.getByTestId('daily-review-submit-btn'));

    expect(screen.getByTestId('daily-review-error')).toHaveTextContent('dailyReview.empty');
    expect(apiRequestMock).not.toHaveBeenCalled();
  });
});

describe('DailyReviewCard agent scope', () => {
  it('stores the review in the selected agent vault and links to that vault pending review', async () => {
    apiRequestMock.mockResolvedValue(STAGED);
    render(<Card agentScopeId="agent-1" />);

    await submitReview();

    expect(apiRequestMock.mock.calls[0][0]).toBe('/wiki/daily-review?agent_id=agent-1');
    expect(await screen.findByTestId('daily-review-goto-pending')).toHaveAttribute(
      'href',
      '/settings/wiki?wikiTab=pendingEdits&agentId=agent-1',
    );
  });

  it('encodes an awkward scope id in the request and in the link', async () => {
    apiRequestMock.mockResolvedValue(STAGED);
    render(<Card agentScopeId="team a/b" />);

    await submitReview();

    expect(apiRequestMock.mock.calls[0][0]).toBe('/wiki/daily-review?agent_id=team%20a%2Fb');
    expect(await screen.findByTestId('daily-review-goto-pending')).toHaveAttribute(
      'href',
      '/settings/wiki?wikiTab=pendingEdits&agentId=team+a%2Fb',
    );
  });

  it('keeps the link on the vault the review went into when the scope switches afterwards', async () => {
    apiRequestMock.mockResolvedValue(STAGED);
    const view = render(<Card agentScopeId="agent-1" />);

    await submitReview();
    view.rerender(<Card agentScopeId="agent-2" />);

    expect(await screen.findByTestId('daily-review-goto-pending')).toHaveAttribute(
      'href',
      '/settings/wiki?wikiTab=pendingEdits&agentId=agent-1',
    );

    await submitReview('Second review', 'Friday');
    expect(apiRequestMock.mock.calls[1][0]).toBe('/wiki/daily-review?agent_id=agent-2');
  });
});

describe('DailyReviewCard failure', () => {
  it.each([
    ['the server rejects the request shape', new ApiError('Validation failed: text too long', 422)],
    ['the server fails while storing it', new ApiError('Failed to store the review: disk I/O error', 500)],
    ['the request never reaches the server', new TypeError('Failed to fetch')],
  ])('shows only the localized message and keeps the text when %s', async (_case, failure) => {
    apiRequestMock.mockRejectedValue(failure);
    render(<Card />);

    await submitReview();

    const error = await screen.findByTestId('daily-review-error');
    expect(error).toHaveTextContent('dailyReview.error');
    expect(error).not.toHaveTextContent(failure.message);
    expect(screen.getByTestId('daily-review-text-input')).toHaveValue('Shipped the fix');
    expect(screen.queryByTestId('daily-review-result')).not.toBeInTheDocument();
  });

  it('names the cause when the security check blocks the review, and keeps the text for editing', async () => {
    const blocked = new ApiError('Review blocked by the security policy', 422, [], undefined, 'security_blocked');
    apiRequestMock.mockRejectedValue(blocked);
    render(<Card />);

    await submitReview();

    const error = await screen.findByTestId('daily-review-error');
    expect(error).toHaveTextContent('dailyReview.securityBlocked');
    expect(error).not.toHaveTextContent(blocked.message);
    expect(screen.getByTestId('daily-review-text-input')).toHaveValue('Shipped the fix');
    expect(screen.queryByTestId('daily-review-result')).not.toBeInTheDocument();
  });
});
