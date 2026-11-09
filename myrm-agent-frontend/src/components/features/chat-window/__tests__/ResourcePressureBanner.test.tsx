/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { deferred } from '@/test-utils/deferred';
import { elapse, settle, startFakeClock, stopFakeClock } from '@/test-utils/fakeClock';

import ResourcePressureBanner from '../ResourcePressureBanner';

const router = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => router }));

const DISMISS_KEY = 'resource_pressure_dismissed';
const POLL_INTERVAL_MS = 60_000;

interface Pressure {
  memory?: { level?: string };
  disk?: { state?: string };
}

const HEALTHY: Pressure = { memory: { level: 'normal' }, disk: { state: 'ok' } };
const MEMORY_WARNING: Pressure = { memory: { level: 'warning' }, disk: { state: 'ok' } };
const MEMORY_CRITICAL: Pressure = { memory: { level: 'critical' }, disk: { state: 'ok' } };

/** Poll N answers with the Nth payload; the last payload repeats for every later poll. */
function answerPolls(...payloads: Pressure[]) {
  const fetchMock = vi.fn(async () => {
    const payload = payloads[Math.min(fetchMock.mock.calls.length - 1, payloads.length - 1)];
    return { ok: true, json: async () => payload };
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

const pollAgain = () => elapse(POLL_INTERVAL_MS);
const bannerTitle = (trigger: string) => screen.queryByText(`trigger.${trigger}.title`);
const storedDismissals = (): unknown => JSON.parse(sessionStorage.getItem(DISMISS_KEY) ?? 'null');

describe('ResourcePressureBanner', () => {
  beforeEach(() => {
    startFakeClock();
    sessionStorage.clear();
    router.push.mockReset();
  });

  afterEach(() => {
    stopFakeClock();
  });

  describe('which pressure it reports', () => {
    it.each<[string, Pressure, string]>([
      [
        'disk-critical above memory-critical',
        { memory: { level: 'critical' }, disk: { state: 'critical' } },
        'disk_critical',
      ],
      [
        'memory emergency as memory-critical',
        { memory: { level: 'emergency' }, disk: { state: 'ok' } },
        'memory_critical',
      ],
      [
        'memory-critical above disk-elevated',
        { memory: { level: 'critical' }, disk: { state: 'elevated' } },
        'memory_critical',
      ],
      [
        'disk-elevated above memory-elevated',
        { memory: { level: 'warning' }, disk: { state: 'elevated' } },
        'disk_elevated',
      ],
      ['memory warning as memory-elevated', MEMORY_WARNING, 'memory_elevated'],
      ['memory level in any letter case', { memory: { level: 'CRITICAL' }, disk: { state: 'OK' } }, 'memory_critical'],
      ['disk state in any letter case', { memory: { level: 'Normal' }, disk: { state: 'Critical' } }, 'disk_critical'],
    ])('reports %s', async (_label, payload, trigger) => {
      answerPolls(payload);
      render(<ResourcePressureBanner />);
      await settle();

      expect(bannerTitle(trigger)).toBeInTheDocument();
      expect(screen.getByText(`trigger.${trigger}.description`)).toBeInTheDocument();
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    it.each<[string, Pressure]>([
      ['everything is fine', HEALTHY],
      ['the answer is empty', {}],
      ['the levels are not ones it knows', { memory: { level: 'mystery' }, disk: { state: 'full-ish' } }],
    ])('stays silent when %s', async (_label, payload) => {
      answerPolls(payload);
      const { container } = render(<ResourcePressureBanner />);
      await settle();

      expect(container).toBeEmptyDOMElement();
    });

    it('stays silent when the pressure service answers with an error status', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn(async () => ({ ok: false, json: async () => MEMORY_CRITICAL })),
      );
      const { container } = render(<ResourcePressureBanner />);
      await settle();

      expect(container).toBeEmptyDOMElement();
    });

    it.each<[string, () => Promise<unknown>]>([
      ['is unreachable', async () => Promise.reject(new Error('offline'))],
      [
        'answers with something that is not JSON',
        async () => ({ ok: true, json: async () => Promise.reject(new SyntaxError('bad json')) }),
      ],
    ])('stays silent when the pressure service %s', async (_label, respond) => {
      vi.stubGlobal('fetch', vi.fn(respond));
      const { container } = render(<ResourcePressureBanner />);
      await settle();

      expect(container).toBeEmptyDOMElement();
    });
  });

  describe('polling', () => {
    it('asks once on mount, then once a minute, and not earlier', async () => {
      const fetchMock = answerPolls(HEALTHY);
      render(<ResourcePressureBanner />);
      await settle();
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(fetchMock).toHaveBeenCalledWith('/api/v1/health/pressure');

      await elapse(POLL_INTERVAL_MS - 1);
      expect(fetchMock).toHaveBeenCalledTimes(1);

      await elapse(1);
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });

    it('follows the pressure as it changes between polls', async () => {
      answerPolls(HEALTHY, MEMORY_WARNING, HEALTHY);
      render(<ResourcePressureBanner />);
      await settle();
      expect(screen.queryByRole('alert')).toBeNull();

      await pollAgain();
      expect(bannerTitle('memory_elevated')).toBeInTheDocument();

      await pollAgain();
      expect(screen.queryByRole('alert')).toBeNull();
    });

    it('stops polling after it unmounts', async () => {
      const fetchMock = answerPolls(HEALTHY);
      const { unmount } = render(<ResourcePressureBanner />);
      await settle();

      unmount();
      await pollAgain();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(vi.getTimerCount()).toBe(0);
    });

    it.each<['response' | 'body']>([['response'], ['body']])(
      'leaves the dismissals alone when the %s of an in-flight poll arrives after it unmounted',
      async (late) => {
        sessionStorage.setItem(DISMISS_KEY, JSON.stringify(['memory_critical']));
        const gate = deferred<void>();
        vi.stubGlobal(
          'fetch',
          vi.fn(async () => {
            if (late === 'response') {
              await gate.promise;
            }
            return {
              ok: true,
              json: async () => {
                if (late === 'body') {
                  await gate.promise;
                }
                return HEALTHY;
              },
            };
          }),
        );
        const { unmount } = render(<ResourcePressureBanner />);
        await settle();

        unmount();
        await act(async () => {
          gate.resolve();
        });

        // A healthy answer that was still allowed to land would clear the stored dismissals.
        expect(storedDismissals()).toEqual(['memory_critical']);
      },
    );
  });

  describe('dismissal', () => {
    it('hides a dismissed trigger for the rest of the session, including after a remount', async () => {
      answerPolls(MEMORY_WARNING);
      const first = render(<ResourcePressureBanner />);
      await settle();

      fireEvent.click(screen.getByRole('button', { name: 'dismiss' }));
      expect(screen.queryByRole('alert')).toBeNull();
      expect(storedDismissals()).toEqual(['memory_elevated']);
      first.unmount();

      const { container } = render(<ResourcePressureBanner />);
      await settle();
      expect(container).toBeEmptyDOMElement();
    });

    it('remembers every trigger dismissed during the session, not only the last one', async () => {
      answerPolls(MEMORY_WARNING, MEMORY_CRITICAL, MEMORY_WARNING);
      render(<ResourcePressureBanner />);
      await settle();
      fireEvent.click(screen.getByRole('button', { name: 'dismiss' }));

      await pollAgain();
      fireEvent.click(screen.getByRole('button', { name: 'dismiss' }));
      expect(storedDismissals()).toEqual(['memory_elevated', 'memory_critical']);

      await pollAgain();
      expect(screen.queryByRole('alert')).toBeNull();
    });

    it('keeps a dismissed trigger hidden for as long as it persists across polls', async () => {
      answerPolls(MEMORY_CRITICAL);
      render(<ResourcePressureBanner />);
      await settle();
      fireEvent.click(screen.getByRole('button', { name: 'dismiss' }));

      await pollAgain();
      await pollAgain();

      expect(screen.queryByRole('alert')).toBeNull();
    });

    it('shows a dismissed trigger again when it escalates from a milder one that is on screen', async () => {
      answerPolls(MEMORY_CRITICAL, MEMORY_WARNING, MEMORY_CRITICAL);
      render(<ResourcePressureBanner />);
      await settle();
      fireEvent.click(screen.getByRole('button', { name: 'dismiss' }));

      await pollAgain();
      expect(bannerTitle('memory_elevated')).toBeInTheDocument();

      await pollAgain();
      expect(bannerTitle('memory_critical')).toBeInTheDocument();
      expect(bannerTitle('memory_elevated')).toBeNull();
    });

    it('takes the banner down when only a dismissed trigger is left after the worse pressure passed', async () => {
      sessionStorage.setItem(DISMISS_KEY, JSON.stringify(['disk_elevated']));
      answerPolls(MEMORY_CRITICAL, { memory: { level: 'normal' }, disk: { state: 'elevated' } });
      render(<ResourcePressureBanner />);
      await settle();
      expect(bannerTitle('memory_critical')).toBeInTheDocument();

      await pollAgain();

      expect(screen.queryByRole('alert')).toBeNull();
    });

    it('clears the dismissals once the pressure is confirmed gone, so the next episode is shown', async () => {
      answerPolls(MEMORY_CRITICAL, HEALTHY, MEMORY_CRITICAL);
      render(<ResourcePressureBanner />);
      await settle();
      fireEvent.click(screen.getByRole('button', { name: 'dismiss' }));
      expect(storedDismissals()).toEqual(['memory_critical']);

      await pollAgain();
      expect(storedDismissals()).toEqual([]);

      await pollAgain();
      expect(bannerTitle('memory_critical')).toBeInTheDocument();
    });

    it.each<[string, string]>([
      ['text that is not JSON', 'not json'],
      ['a JSON object', '{"memory_elevated":true}'],
      ['a JSON string', '"memory_elevated"'],
    ])('ignores a dismissal record that is %s', async (_label, record) => {
      sessionStorage.setItem(DISMISS_KEY, record);
      answerPolls(MEMORY_WARNING);
      render(<ResourcePressureBanner />);
      await settle();

      expect(bannerTitle('memory_elevated')).toBeInTheDocument();
    });

    it('honors the valid entries of a record that also holds junk', async () => {
      sessionStorage.setItem(DISMISS_KEY, JSON.stringify(['memory_elevated', 7, null]));
      answerPolls(MEMORY_WARNING);
      const { container } = render(<ResourcePressureBanner />);
      await settle();

      expect(container).toBeEmptyDOMElement();
    });

    it('still hides the banner when the dismissal cannot be stored', async () => {
      answerPolls(MEMORY_WARNING);
      render(<ResourcePressureBanner />);
      await settle();
      vi.stubGlobal('sessionStorage', {
        getItem: () => null,
        setItem: () => {
          throw new Error('QuotaExceededError');
        },
      });

      fireEvent.click(screen.getByRole('button', { name: 'dismiss' }));

      expect(screen.queryByRole('alert')).toBeNull();
    });
  });

  it('opens the system settings from the banner', async () => {
    answerPolls(MEMORY_CRITICAL);
    render(<ResourcePressureBanner />);
    await settle();

    fireEvent.click(screen.getByRole('button', { name: 'open' }));

    expect(router.push).toHaveBeenCalledWith('/settings/system?sub=about');
  });
});
