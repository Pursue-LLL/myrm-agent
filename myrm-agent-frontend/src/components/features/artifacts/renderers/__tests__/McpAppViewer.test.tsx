/** @vitest-environment jsdom */
import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest';

import * as tauriModule from '@/lib/tauri';
import type { McpAppView } from '@/store/chat/types';
import { useExternalLinkConfirmStore } from '@/store/useExternalLinkConfirmStore';
import { McpAppViewer } from '../McpAppViewer';

const { fetchWithTimeout } = vi.hoisted(() => ({ fetchWithTimeout: vi.fn() }));

vi.mock('@/lib/api', () => ({ fetchWithTimeout }));

const VIEW: McpAppView = { resourceUri: 'ui://linear/board', serverName: 'Linear' };
const LINK_TYPES = ['openLink', 'app:openLink', 'widget-navigate'] as const;
const UNSAFE_URLS = [
  { label: 'javascript scheme', url: 'javascript:alert(document.domain)' },
  { label: 'data scheme', url: 'data:text/html,<script>alert(1)</script>' },
  { label: 'file scheme', url: 'file:///etc/passwd' },
  { label: 'custom scheme', url: 'cursor://settings' },
];

/** Renders the viewer and waits for the app iframe; the shared next-intl test mock returns message keys as text. */
async function renderViewer(): Promise<HTMLIFrameElement> {
  render(<McpAppViewer view={VIEW} />);
  return (await screen.findByTitle('title')) as HTMLIFrameElement;
}

/** Delivers a message to the host window, tagged with the sender window like the browser does. */
function postMessageFrom(source: Window | null, data: unknown): void {
  act(() => {
    window.dispatchEvent(new MessageEvent('message', { data, source }));
  });
}

function pendingPrompt() {
  const { open, link } = useExternalLinkConfirmStore.getState();
  return { open, link };
}

describe('McpAppViewer link relay', () => {
  let openSpy: MockInstance<Window['open']>;
  let warnSpy: MockInstance<Console['warn']>;
  let isTauri: MockInstance<typeof tauriModule.isTauriEnvironment>;

  beforeEach(() => {
    useExternalLinkConfirmStore.setState({ open: false, link: null, declinedAt: 0 });
    fetchWithTimeout.mockResolvedValue({
      ok: true,
      json: async () => ({ data: { content: btoa('<p>app</p>') } }),
    });
    openSpy = vi.spyOn(window, 'open').mockReturnValue(null);
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    isTauri = vi.spyOn(tauriModule, 'isTauriEnvironment').mockReturnValue(false);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    fetchWithTimeout.mockReset();
  });

  describe('in a browser', () => {
    it.each(LINK_TYPES)('opens an http(s) link sent as %s in a new tab', async (type) => {
      const iframe = await renderViewer();

      postMessageFrom(iframe.contentWindow, { type, url: 'https://example.com/docs?q=1' });

      expect(openSpy).toHaveBeenCalledExactlyOnceWith('https://example.com/docs?q=1', '_blank', 'noopener,noreferrer');
      expect(pendingPrompt().open).toBe(false);
    });
  });

  describe('in the desktop shell', () => {
    beforeEach(() => {
      isTauri.mockReturnValue(true);
    });

    it.each(LINK_TYPES)('asks the user, naming the MCP server, for a link sent as %s', async (type) => {
      const iframe = await renderViewer();

      postMessageFrom(iframe.contentWindow, { type, url: 'https://example.com/docs?q=1' });

      expect(openSpy).not.toHaveBeenCalled();
      expect(pendingPrompt()).toEqual({
        open: true,
        link: { url: 'https://example.com/docs?q=1', source: 'Linear' },
      });
    });
  });

  describe.each([
    { shell: 'a browser', tauri: false },
    { shell: 'the desktop shell', tauri: true },
  ])('in $shell', ({ tauri }) => {
    beforeEach(() => {
      isTauri.mockReturnValue(tauri);
    });

    it.each(UNSAFE_URLS)('blocks an app link with a $label', async ({ url }) => {
      const iframe = await renderViewer();

      postMessageFrom(iframe.contentWindow, { type: 'openLink', url });

      expect(openSpy).not.toHaveBeenCalled();
      expect(pendingPrompt().open).toBe(false);
      expect(warnSpy).toHaveBeenCalledExactlyOnceWith('[untrusted-link] Blocked external link request:', url);
    });

    it('ignores a link request without a url string', async () => {
      const iframe = await renderViewer();

      postMessageFrom(iframe.contentWindow, { type: 'openLink', url: 42 });
      postMessageFrom(iframe.contentWindow, { type: 'openLink' });

      expect(openSpy).not.toHaveBeenCalled();
      expect(pendingPrompt().open).toBe(false);
      expect(warnSpy).not.toHaveBeenCalled();
    });

    it('ignores link requests that do not come from its own iframe', async () => {
      await renderViewer();

      postMessageFrom(window, { type: 'openLink', url: 'https://example.com' });

      expect(openSpy).not.toHaveBeenCalled();
      expect(pendingPrompt().open).toBe(false);
    });
  });
});
