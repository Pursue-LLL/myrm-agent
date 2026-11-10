/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Mock } from 'vitest';
import { printHtmlDocument } from '../printHtmlDocument';

const LOAD_WAIT_MS = 1500;
const FONT_WAIT_MS = 3000;
const FRAME_LIFETIME_MS = 3000;
const PAGE = '<!doctype html><html><body><p>Exported chat</p></body></html>';

describe('printHtmlDocument', () => {
  let print: Mock<() => void>;

  /** jsdom has no FontFaceSet; a test that wants one gives it to the document of the iframe that is printing. */
  function defineFonts(ready: Promise<unknown>): void {
    const printedDocument = document.querySelector('iframe')?.contentDocument;
    if (!printedDocument) {
      throw new Error('the print iframe has no document');
    }
    Object.defineProperty(printedDocument, 'fonts', { value: { ready } });
  }

  beforeEach(() => {
    // Only the timers the print flow waits on are faked, so jsdom keeps loading the iframe the way it does for real.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    print = vi.fn();
    // jsdom does not implement printing.
    vi.spyOn(HTMLIFrameElement.prototype, 'contentWindow', 'get').mockReturnValue({ print } as unknown as Window);
  });
  afterEach(() => {
    document.body.innerHTML = '';
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('writes the document into a hidden iframe', async () => {
    const printing = printHtmlDocument(PAGE);

    const frame = document.querySelector('iframe');
    expect(frame?.contentDocument?.body.textContent).toBe('Exported chat');
    expect(frame?.style.position).toBe('fixed');

    await vi.advanceTimersByTimeAsync(LOAD_WAIT_MS);
    await printing;
  });

  it('prints only after the fonts of the document are ready', async () => {
    let fontsLoaded!: () => void;
    const printing = printHtmlDocument(PAGE);
    defineFonts(new Promise<void>((resolve) => (fontsLoaded = resolve)));

    await vi.advanceTimersByTimeAsync(LOAD_WAIT_MS);
    expect(print).not.toHaveBeenCalled();

    fontsLoaded();
    await printing;
    expect(print).toHaveBeenCalledTimes(1);
  });

  it('stops waiting for fonts that never get ready', async () => {
    const printing = printHtmlDocument(PAGE);
    defineFonts(new Promise<void>(() => undefined));

    await vi.advanceTimersByTimeAsync(LOAD_WAIT_MS + FONT_WAIT_MS - 1);
    expect(print).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(print).toHaveBeenCalledTimes(1);
    await printing;
  });

  it('prints once the load wait is over where the browser has no font loading API', async () => {
    const printing = printHtmlDocument(PAGE);

    await vi.advanceTimersByTimeAsync(LOAD_WAIT_MS);

    expect(print).toHaveBeenCalledTimes(1);
    await printing;
  });

  it('removes the iframe after the print dialog has had time to take the document', async () => {
    const printing = printHtmlDocument(PAGE);
    await vi.advanceTimersByTimeAsync(LOAD_WAIT_MS);
    await printing;

    expect(document.querySelector('iframe')).not.toBeNull();
    await vi.advanceTimersByTimeAsync(FRAME_LIFETIME_MS);
    expect(document.querySelector('iframe')).toBeNull();
  });

  it('fails and removes the iframe when its document cannot be reached', async () => {
    vi.spyOn(HTMLIFrameElement.prototype, 'contentDocument', 'get').mockReturnValue(null);
    vi.spyOn(HTMLIFrameElement.prototype, 'contentWindow', 'get').mockReturnValue(null);

    await expect(printHtmlDocument(PAGE)).rejects.toThrow('Failed to access iframe document');

    expect(document.querySelector('iframe')).toBeNull();
  });
});
