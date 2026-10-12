/** @vitest-environment jsdom */
import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest';

import { HtmlPreview } from '../MediaPreview';

vi.mock('@/components/features/image-editor/uploadAnnotated', () => ({
  uploadAnnotatedImage: vi.fn(),
}));

const UNSAFE_URLS = [
  { label: 'javascript scheme', url: 'javascript:alert(document.domain)' },
  { label: 'data scheme', url: 'data:text/html,<script>alert(1)</script>' },
  { label: 'file scheme', url: 'file:///etc/passwd' },
  { label: 'mail scheme', url: 'mailto:someone@example.com' },
  { label: 'custom scheme', url: 'cursor://settings' },
];

function renderWidget(): HTMLIFrameElement {
  render(<HtmlPreview content="<a href='https://example.com'>link</a>" />);
  return screen.getByTitle('HTML Preview') as HTMLIFrameElement;
}

/** Delivers a message to the host window, tagged with the sender window like the browser does. */
function postMessageFrom(source: Window | null, data: unknown): void {
  act(() => {
    window.dispatchEvent(new MessageEvent('message', { data, source }));
  });
}

describe('HtmlPreview widget-navigate relay', () => {
  let openSpy: MockInstance<Window['open']>;
  let warnSpy: MockInstance<Console['warn']>;

  beforeEach(() => {
    openSpy = vi.spyOn(window, 'open').mockReturnValue(null);
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('opens an http(s) link requested by the widget in a new tab', () => {
    const iframe = renderWidget();

    postMessageFrom(iframe.contentWindow, { type: 'widget-navigate', url: 'https://example.com/docs?q=1' });

    expect(openSpy).toHaveBeenCalledExactlyOnceWith('https://example.com/docs?q=1', '_blank', 'noopener,noreferrer');
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it.each(UNSAFE_URLS)('blocks a widget link with a $label', ({ url }) => {
    const iframe = renderWidget();

    postMessageFrom(iframe.contentWindow, { type: 'widget-navigate', url });

    expect(openSpy).not.toHaveBeenCalled();
    expect(warnSpy).toHaveBeenCalledExactlyOnceWith(
      '[HtmlPreview] Blocked unsafe external link navigation attempt:',
      url,
    );
  });

  it('ignores a navigation request that does not carry a url string', () => {
    const iframe = renderWidget();

    postMessageFrom(iframe.contentWindow, { type: 'widget-navigate', url: 42 });

    expect(openSpy).not.toHaveBeenCalled();
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it('ignores navigation requests that do not come from its own iframe', () => {
    renderWidget();

    postMessageFrom(window, { type: 'widget-navigate', url: 'https://example.com' });

    expect(openSpy).not.toHaveBeenCalled();
  });
});
