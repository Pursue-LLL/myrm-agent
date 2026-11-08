/** @vitest-environment jsdom */
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ImportUrlsResultResponse, UrlImportItemResult } from '@/services/wikiService';
import type { MockLocale } from '@/test-utils/realIntl';

let locale: MockLocale = 'en';
vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => locale));

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

const importUrls = vi.hoisted(() => vi.fn());
vi.mock('@/services/wikiService', () => ({ wikiService: { importUrls } }));

import { WikiUrlImportDialog } from '../WikiUrlImportDialog';

const OK_URL = 'https://ok.example/a';
const BAD_URL = 'https://bad.example/b';
const BAD_REASON = 'No readable content could be fetched from https://bad.example/b';

function item(url: string, status: UrlImportItemResult['status'], error = ''): UrlImportItemResult {
  return { url, relative_path: status === 'error' ? '' : `${url.split('/').pop()}.md`, status, error };
}

function responseFor(results: UrlImportItemResult[]): ImportUrlsResultResponse {
  const count = (status: UrlImportItemResult['status']) => results.filter((entry) => entry.status === status).length;
  return {
    success: true,
    total_urls: results.length,
    processed_count: results.length,
    enqueued_count: count('success') + count('superseded') + count('security_redacted'),
    skipped_conflict_count: count('skipped_conflict'),
    superseded_count: count('superseded'),
    security_blocked_count: count('security_blocked'),
    security_redacted_count: count('security_redacted'),
    error_count: count('error'),
    results,
    message: '',
  };
}

const PARTIAL_FAILURE = responseFor([item(OK_URL, 'success'), item(BAD_URL, 'error', BAD_REASON)]);

const LABELS: Record<MockLocale, { placeholder: string; start: string }> = {
  en: { placeholder: 'Paste URLs here (one per line, up to 50)', start: 'Start Ingestion' },
  zh: { placeholder: '在此粘贴链接（每行一个，最多 50 个）', start: '开始摄入' },
};

function renderDialog() {
  const onOpenChange = vi.fn();
  const onImportFinished = vi.fn();
  render(<WikiUrlImportDialog open onOpenChange={onOpenChange} onImportFinished={onImportFinished} />);
  const user = userEvent.setup();
  const box = screen.getByPlaceholderText(LABELS[locale].placeholder) as HTMLTextAreaElement;
  return { user, box, onOpenChange, onImportFinished };
}

function startButton() {
  return screen.getByRole('button', { name: LABELS[locale].start });
}

async function pasteAndStart(view: ReturnType<typeof renderDialog>, text: string) {
  await view.user.click(view.box);
  await view.user.paste(text);
  await view.user.click(startButton());
  await waitFor(() => expect(view.onImportFinished).toHaveBeenCalled());
}

describe('WikiUrlImportDialog', () => {
  beforeEach(() => {
    locale = 'en';
    importUrls.mockResolvedValue(responseFor([item(OK_URL, 'success')]));
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it('sends each well-formed http(s) link once, in order, and nothing else', async () => {
    const view = renderDialog();

    await pasteAndStart(
      view,
      [
        '  https://example.com/a  ',
        '',
        'javascript:alert(1)',
        'file:///etc/passwd',
        'https://example.com/b',
        'https://example.com/a',
      ].join('\n'),
    );

    expect(importUrls).toHaveBeenCalledWith(
      ['https://example.com/a', 'https://example.com/b'],
      undefined,
      true,
      undefined,
    );
  });

  it('closes and clears the box when every link was imported', async () => {
    const view = renderDialog();

    await pasteAndStart(view, OK_URL);

    expect(view.onOpenChange).toHaveBeenCalledWith(false);
    expect(view.box.value).toBe('');
    expect(toast.success).toHaveBeenCalledWith('Import complete: 1 total, 1 enqueued, 0 errors');
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('treats skipped, superseded, redacted and blocked links as finished, not as failures', async () => {
    importUrls.mockResolvedValue(
      responseFor([
        item(OK_URL, 'skipped_conflict'),
        item('https://x.example/1', 'superseded'),
        item('https://x.example/2', 'security_redacted'),
        item('https://x.example/3', 'security_blocked'),
      ]),
    );
    const view = renderDialog();

    await pasteAndStart(view, [OK_URL, 'https://x.example/1', 'https://x.example/2', 'https://x.example/3'].join('\n'));

    expect(view.onOpenChange).toHaveBeenCalledWith(false);
    expect(toast.warning).not.toHaveBeenCalled();
  });

  describe('after a partly failed batch', () => {
    beforeEach(() => {
      importUrls.mockResolvedValue(PARTIAL_FAILURE);
    });

    it('stays open with only the failed link in the box and warns instead of celebrating', async () => {
      const view = renderDialog();

      await pasteAndStart(view, `${OK_URL}\n${BAD_URL}`);

      expect(view.onOpenChange).not.toHaveBeenCalled();
      expect(view.box.value).toBe(BAD_URL);
      expect(toast.warning).toHaveBeenCalledWith('Import complete: 2 total, 1 enqueued, 1 errors');
      expect(toast.success).not.toHaveBeenCalled();
    });

    it('lists the failed link with its reason and the retry hint, but not the imported one', async () => {
      const view = renderDialog();

      await pasteAndStart(view, `${OK_URL}\n${BAD_URL}`);

      const panel = screen.getByRole('alert');
      expect(within(panel).getByText(/These links could not be imported/)).toBeInTheDocument();
      expect(within(panel).getByText(BAD_URL)).toBeInTheDocument();
      expect(within(panel).getByText(new RegExp(BAD_REASON))).toBeInTheDocument();
      expect(within(panel).queryByText(OK_URL)).toBeNull();
    });

    it('retries only the failed link on the next click and closes once it is imported', async () => {
      const view = renderDialog();
      await pasteAndStart(view, `${OK_URL}\n${BAD_URL}`);
      importUrls.mockResolvedValue(responseFor([item(BAD_URL, 'success')]));

      await view.user.click(startButton());

      await waitFor(() => expect(view.onOpenChange).toHaveBeenCalledWith(false));
      expect(importUrls).toHaveBeenLastCalledWith([BAD_URL], undefined, true, undefined);
      expect(screen.queryByRole('alert')).toBeNull();
    });

    it('stops listing a failure once its link is removed from the box', async () => {
      const view = renderDialog();
      await pasteAndStart(view, `${OK_URL}\n${BAD_URL}`);
      expect(screen.getByRole('alert')).toBeInTheDocument();

      await view.user.clear(view.box);

      expect(screen.queryByRole('alert')).toBeNull();
    });

    it('shows the retry hint in the language of the interface', async () => {
      locale = 'zh';
      const view = renderDialog();

      await pasteAndStart(view, `${OK_URL}\n${BAD_URL}`);

      expect(
        within(screen.getByRole('alert')).getByText('以下链接未能导入，已保留在输入框中，可检查后重试。'),
      ).toBeInTheDocument();
    });
  });

  it('keeps the links beyond the batch limit in the box for the next batch', async () => {
    const urls = Array.from({ length: 52 }, (_, index) => `https://example.com/post-${index + 1}`);
    importUrls.mockResolvedValue(responseFor(urls.slice(0, 50).map((url) => item(url, 'success'))));
    const view = renderDialog();

    await pasteAndStart(view, urls.join('\n'));

    expect(importUrls).toHaveBeenCalledWith(urls.slice(0, 50), undefined, true, undefined);
    expect(toast.warning).toHaveBeenCalledWith('Maximum 50 URLs allowed per batch import');
    expect(view.onOpenChange).not.toHaveBeenCalled();
    expect(view.box.value).toBe(urls.slice(50).join('\n'));
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('reports a request that failed outright and keeps the box as it was', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    importUrls.mockRejectedValue(new Error('network down'));
    const view = renderDialog();

    await view.user.click(view.box);
    await view.user.paste(OK_URL);
    await view.user.click(startButton());

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Failed to start URL batch import'));
    expect(view.onOpenChange).not.toHaveBeenCalled();
    expect(view.box.value).toBe(OK_URL);
  });
});
