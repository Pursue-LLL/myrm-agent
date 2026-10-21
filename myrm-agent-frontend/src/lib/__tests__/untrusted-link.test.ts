/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest';

import * as tauriModule from '@/lib/tauri';
import { requestUntrustedLink } from '@/lib/untrusted-link';
import { useExternalLinkConfirmStore } from '@/store/useExternalLinkConfirmStore';

const UNSAFE_URLS = [
  { label: 'javascript scheme', url: 'javascript:alert(document.domain)' },
  { label: 'data scheme', url: 'data:text/html,<script>alert(1)</script>' },
  { label: 'file scheme', url: 'file:///etc/passwd' },
  { label: 'mail scheme', url: 'mailto:someone@example.com' },
  { label: 'custom scheme', url: 'cursor://settings' },
  { label: 'relative path', url: '/settings' },
  { label: 'empty string', url: '' },
];

/** Longest address the prompt accepts, so it can always be shown in full. */
const MAX_URL_LENGTH = 8192;

function urlOfLength(length: number): string {
  const prefix = 'https://example.com/';
  return prefix + 'a'.repeat(length - prefix.length);
}

function pendingPrompt() {
  const { open, link } = useExternalLinkConfirmStore.getState();
  return { open, link };
}

describe('requestUntrustedLink', () => {
  let openSpy: MockInstance<Window['open']>;
  let warnSpy: MockInstance<Console['warn']>;

  beforeEach(() => {
    useExternalLinkConfirmStore.setState({ open: false, link: null, declinedAt: 0 });
    openSpy = vi.spyOn(window, 'open').mockReturnValue(null);
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('in a browser', () => {
    beforeEach(() => {
      vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(false);
    });

    it('opens an http(s) link in a new tab without asking', () => {
      requestUntrustedLink('https://example.com/docs?q=1', 'Linear');

      expect(openSpy).toHaveBeenCalledExactlyOnceWith('https://example.com/docs?q=1', '_blank', 'noopener,noreferrer');
      expect(pendingPrompt()).toEqual({ open: false, link: null });
    });

    it('opens the normalized address', () => {
      requestUntrustedLink('  https://Example.COM/a b  ', null);

      expect(openSpy).toHaveBeenCalledExactlyOnceWith('https://example.com/a%20b', '_blank', 'noopener,noreferrer');
    });
  });

  describe('in the desktop shell', () => {
    beforeEach(() => {
      vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(true);
    });

    it('asks the user instead of opening, naming the requesting app', () => {
      requestUntrustedLink('https://example.com/docs?q=1', 'Linear');

      expect(openSpy).not.toHaveBeenCalled();
      expect(pendingPrompt()).toEqual({
        open: true,
        link: { url: 'https://example.com/docs?q=1', source: 'Linear' },
      });
    });

    it('shows the punycode form of a lookalike host, which is what the browser would receive', () => {
      requestUntrustedLink('https://аpple.com/login', null);

      expect(pendingPrompt().link?.url).toBe('https://xn--pple-43d.com/login');
    });

    it('keeps the first prompt when more requests arrive, as a flooding page would send', () => {
      for (let attempt = 1; attempt <= 5; attempt += 1) {
        requestUntrustedLink(`https://example.com/hit/${attempt}`, null);
      }

      expect(openSpy).not.toHaveBeenCalled();
      expect(pendingPrompt().link?.url).toBe('https://example.com/hit/1');
    });

    it('accepts an address of the maximum length and refuses one character more', () => {
      requestUntrustedLink(urlOfLength(MAX_URL_LENGTH + 1), null);
      expect(pendingPrompt()).toEqual({ open: false, link: null });

      requestUntrustedLink(urlOfLength(MAX_URL_LENGTH), null);
      expect(pendingPrompt().open).toBe(true);
    });
  });

  describe.each([
    { shell: 'a browser', isTauri: false },
    { shell: 'the desktop shell', isTauri: true },
  ])('in $shell', ({ isTauri }) => {
    beforeEach(() => {
      vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(isTauri);
    });

    it.each(UNSAFE_URLS)('blocks a $label link', ({ url }) => {
      requestUntrustedLink(url, 'Linear');

      expect(openSpy).not.toHaveBeenCalled();
      expect(pendingPrompt()).toEqual({ open: false, link: null });
      expect(warnSpy).toHaveBeenCalledExactlyOnceWith('[untrusted-link] Blocked external link request:', url);
    });

    it('logs only a bounded prefix of an oversized request', () => {
      const oversized = urlOfLength(MAX_URL_LENGTH + 1);

      requestUntrustedLink(oversized, null);

      expect(warnSpy).toHaveBeenCalledExactlyOnceWith(
        '[untrusted-link] Blocked external link request:',
        oversized.slice(0, 200),
      );
    });
  });
});
