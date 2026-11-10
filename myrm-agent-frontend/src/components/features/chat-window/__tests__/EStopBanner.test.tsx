import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { deferred } from '@/test-utils/deferred';
import EStopBanner from '../EStopBanner';

type EStopStatus = { level: string; reason: string };
type Request = { method?: string; body?: string };

const kit = vi.hoisted(() => ({
  apiRequest: vi.fn<(path: string, options?: { method?: string; body?: string }) => Promise<EStopStatus>>(),
  toast: vi.fn<(key: string, values: undefined, options: { type: string }) => void>(),
}));

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiRequest: kit.apiRequest,
}));
vi.mock('@/services/i18nToastService', () => ({ showI18nToast: kit.toast }));

const frozen = (reason = 'Spending limit reached'): EStopStatus => ({ level: 'hard', reason });
const running: EStopStatus = { level: 'none', reason: '' };

/** Answers every status read with `status`, and a resume with a running system. */
function serve(status: EStopStatus): void {
  kit.apiRequest.mockImplementation(async (_path, options) => (options?.method === 'POST' ? running : status));
}

async function mount() {
  const view = render(<EStopBanner />);
  await act(async () => undefined);
  return view;
}

const resumeButton = () => screen.getByRole('button', { name: 'resume' });
const requests = (): Request[] => kit.apiRequest.mock.calls.map(([, options]) => options ?? {});

beforeEach(() => {
  serve(running);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('EStopBanner status', () => {
  it('reads the emergency stop status when it appears', async () => {
    await mount();

    expect(kit.apiRequest).toHaveBeenCalledExactlyOnceWith('/security/estop');
  });

  it('shows nothing while the system is running', async () => {
    const { container } = await mount();

    expect(container).toBeEmptyDOMElement();
  });

  it('shows an alert with the reason while the system is frozen', async () => {
    serve(frozen('Spending limit reached'));
    await mount();

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('message')).toBeInTheDocument();
    expect(screen.getByText('Spending limit reached')).toBeInTheDocument();
  });

  it.each([[''], ['   ']])('falls back to a general hint when the reason is %j', async (reason) => {
    serve(frozen(reason));
    await mount();

    expect(screen.getByText('hint')).toBeInTheDocument();
  });

  it('shows nothing when the status cannot be read', async () => {
    kit.apiRequest.mockRejectedValue(new Error('offline'));
    const { container } = await mount();

    expect(container).toBeEmptyDOMElement();
  });

  it('hides the banner when a later read fails, rather than showing a status it can no longer vouch for', async () => {
    serve(frozen());
    const { container } = await mount();
    kit.apiRequest.mockRejectedValueOnce(new Error('offline'));

    await act(async () => void window.dispatchEvent(new Event('focus')));

    expect(container).toBeEmptyDOMElement();
  });

  it('shows what the server says is current when the window gets focus', async () => {
    const { container } = await mount();
    serve(frozen());

    await act(async () => void window.dispatchEvent(new Event('focus')));
    expect(screen.getByRole('alert')).toBeInTheDocument();

    serve(running);
    await act(async () => void window.dispatchEvent(new Event('focus')));
    expect(container).toBeEmptyDOMElement();
  });

  it('shows what the server says is current when the status is announced as changed', async () => {
    await mount();
    serve(frozen());

    await act(async () => void window.dispatchEvent(new Event('estop-changed')));

    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('stops listening when it goes away', async () => {
    const { unmount } = await mount();
    unmount();
    kit.apiRequest.mockClear();

    await act(async () => {
      window.dispatchEvent(new Event('focus'));
      window.dispatchEvent(new Event('estop-changed'));
    });

    expect(kit.apiRequest).not.toHaveBeenCalled();
  });

  it('keeps the newest answer when an older read finishes last', async () => {
    const older = deferred<EStopStatus>();
    kit.apiRequest.mockReturnValueOnce(older.promise);
    const { container } = render(<EStopBanner />);

    serve(running);
    await act(async () => void window.dispatchEvent(new Event('focus')));
    await act(async () => older.resolve(frozen()));

    expect(container).toBeEmptyDOMElement();
  });
});

describe('EStopBanner resuming', () => {
  beforeEach(() => serve(frozen()));

  it('asks the server to resume, hides the banner and confirms', async () => {
    const { container } = await mount();
    serve(running);

    fireEvent.click(resumeButton());
    await act(async () => undefined);

    expect(requests()).toContainEqual({ method: 'POST', body: JSON.stringify({ action: 'resume' }) });
    expect(container).toBeEmptyDOMElement();
    expect(kit.toast).toHaveBeenCalledExactlyOnceWith('commands.builtin.freezeResumed', undefined, { type: 'success' });
  });

  it('hides the banner as soon as the server accepts, without waiting to read the status again', async () => {
    const { container } = await mount();
    const reread = deferred<EStopStatus>();
    kit.apiRequest.mockResolvedValueOnce(running).mockReturnValueOnce(reread.promise);

    fireEvent.click(resumeButton());
    await act(async () => undefined);

    expect(container).toBeEmptyDOMElement();
    await act(async () => reread.resolve(running));
  });

  it('announces the change so the rest of the app can look again', async () => {
    await mount();
    serve(running);
    const announced = vi.fn();
    window.addEventListener('estop-changed', announced);

    fireEvent.click(resumeButton());
    await act(async () => undefined);
    window.removeEventListener('estop-changed', announced);

    expect(announced).toHaveBeenCalledTimes(1);
  });

  it('disables the button and says it is resuming until the server answers', async () => {
    await mount();
    const answer = deferred<EStopStatus>();
    kit.apiRequest.mockReturnValueOnce(answer.promise);

    fireEvent.click(resumeButton());
    await act(async () => undefined);

    expect(screen.getByRole('button', { name: 'resuming' })).toBeDisabled();
    await act(async () => answer.resolve(running));
  });

  it('keeps the banner, says it failed and gives the button back when the server refuses', async () => {
    await mount();
    kit.apiRequest.mockRejectedValueOnce(new Error('denied'));

    fireEvent.click(resumeButton());
    await act(async () => undefined);

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(resumeButton()).toBeEnabled();
    expect(kit.toast).toHaveBeenCalledExactlyOnceWith('commands.builtin.freezeFailed', undefined, { type: 'error' });
  });
});
