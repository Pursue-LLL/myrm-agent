import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  DECLINE_QUIET_PERIOD_MS,
  useExternalLinkConfirmStore,
  type PendingExternalLink,
} from '@/store/useExternalLinkConfirmStore';

const FIRST: PendingExternalLink = { url: 'https://example.com/first', source: 'Linear' };
const SECOND: PendingExternalLink = { url: 'https://example.org/second', source: null };

function snapshot() {
  const { open, link, declinedAt } = useExternalLinkConfirmStore.getState();
  return { open, link, declinedAt };
}

describe('useExternalLinkConfirmStore', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'));
    useExternalLinkConfirmStore.setState({ open: false, link: null, declinedAt: 0 });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('opens the prompt for the first request', () => {
    useExternalLinkConfirmStore.getState().request(FIRST);

    expect(snapshot()).toEqual({ open: true, link: FIRST, declinedAt: 0 });
  });

  it('drops requests while a prompt is open and keeps the one on screen', () => {
    const { request } = useExternalLinkConfirmStore.getState();
    request(FIRST);
    request(SECOND);

    expect(snapshot().link).toBe(FIRST);
  });

  it('closes on approval without starting the quiet period', () => {
    const { request, approve } = useExternalLinkConfirmStore.getState();
    request(FIRST);
    approve();

    expect(snapshot()).toEqual({ open: false, link: FIRST, declinedAt: 0 });

    request(SECOND);
    expect(snapshot()).toEqual({ open: true, link: SECOND, declinedAt: 0 });
  });

  it('closes on refusal and drops requests during the quiet period', () => {
    const { request, decline } = useExternalLinkConfirmStore.getState();
    request(FIRST);
    decline();

    expect(snapshot().open).toBe(false);
    expect(snapshot().declinedAt).toBe(Date.now());

    vi.advanceTimersByTime(DECLINE_QUIET_PERIOD_MS - 1);
    request(SECOND);
    expect(snapshot()).toMatchObject({ open: false, link: FIRST });
  });

  it('accepts requests again once the quiet period has passed', () => {
    const { request, decline } = useExternalLinkConfirmStore.getState();
    request(FIRST);
    decline();

    vi.advanceTimersByTime(DECLINE_QUIET_PERIOD_MS);
    request(SECOND);

    expect(snapshot()).toMatchObject({ open: true, link: SECOND });
  });

  it('prompts again when the clock stepped back after a refusal, then re-arms the quiet period', () => {
    const { request, decline } = useExternalLinkConfirmStore.getState();
    request(FIRST);
    decline();

    vi.setSystemTime(Date.now() - 60_000);
    request(SECOND);
    expect(snapshot()).toMatchObject({ open: true, link: SECOND });

    decline();
    vi.advanceTimersByTime(DECLINE_QUIET_PERIOD_MS - 1);
    request(FIRST);
    expect(snapshot()).toMatchObject({ open: false, link: SECOND });
  });

  it('ignores a refusal when no prompt is open, so approval followed by the close callback stays clean', () => {
    const { request, approve, decline } = useExternalLinkConfirmStore.getState();
    request(FIRST);
    approve();
    decline();

    expect(snapshot().declinedAt).toBe(0);
    request(SECOND);
    expect(snapshot().open).toBe(true);
  });
});
