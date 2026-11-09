/** @vitest-environment jsdom */
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ImportVideoResponse, UrlImportErrorCode } from '@/services/wikiService';
import type { MockLocale } from '@/test-utils/realIntl';

let locale: MockLocale = 'en';
vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => locale));

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), message: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

const importVideo = vi.hoisted(() => vi.fn());
vi.mock('@/services/wikiService', () => ({ wikiService: { importVideo } }));

import { WikiVideoImportDialog } from '../WikiVideoImportDialog';

const VIDEO_URL = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ';

function failure(over: Partial<ImportVideoResponse>): ImportVideoResponse {
  return {
    success: false,
    url: VIDEO_URL,
    relative_path: '',
    status: 'error',
    // The server's English diagnostic, which the dialog must never show.
    error: `Could not fetch subtitles for the YouTube video, or it has no subtitles: ${VIDEO_URL}`,
    error_code: null,
    message: 'Video transcript unavailable',
    ...over,
  };
}

const LABELS: Record<MockLocale, { placeholder: string; start: string }> = {
  en: {
    placeholder: 'https://www.bilibili.com/video/BV... or https://www.youtube.com/watch?v=...',
    start: 'Start Ingesting',
  },
  zh: {
    placeholder: 'https://www.bilibili.com/video/BV... 或 https://www.youtube.com/watch?v=...',
    start: '开始解析入库',
  },
};

const REASONS: Record<MockLocale, Record<UrlImportErrorCode, string>> = {
  en: {
    address_rejected: 'This address cannot be imported. Check that it is a public web link.',
    nothing_readable: 'No subtitles could be fetched for this video. Check that it is public and has subtitles.',
    import_failed: 'The import failed. Try again later.',
  },
  zh: {
    address_rejected: '该地址无法导入，请确认它是可公开访问的网页链接。',
    nothing_readable: '没有获取到这个视频的字幕，请确认视频已公开且带有字幕。',
    import_failed: '导入失败，请稍后重试。',
  },
};
const ERROR_CODES: UrlImportErrorCode[] = ['address_rejected', 'nothing_readable', 'import_failed'];

const BLOCKED: Record<MockLocale, string> = {
  en: '1 file(s) were blocked because they contain credentials or other sensitive content.',
  zh: '有 1 个文件因含凭证或其他敏感内容被拒绝导入。',
};

const KEPT: Record<MockLocale, string> = {
  en: 'A source file for this video already exists. It was kept and nothing new was added.',
  zh: '这个视频的来源文件已存在，已保留原有内容，本次没有新增。',
};

function renderDialog() {
  const onOpenChange = vi.fn();
  const onImportFinished = vi.fn();
  render(<WikiVideoImportDialog open onOpenChange={onOpenChange} onImportFinished={onImportFinished} />);
  const user = userEvent.setup();
  const box = screen.getByPlaceholderText(LABELS[locale].placeholder) as HTMLInputElement;
  return { user, box, onOpenChange, onImportFinished };
}

async function submit(view: ReturnType<typeof renderDialog>) {
  await view.user.click(view.box);
  await view.user.paste(VIDEO_URL);
  await view.user.click(screen.getByRole('button', { name: LABELS[locale].start }));
}

describe('WikiVideoImportDialog', () => {
  afterEach(() => {
    cleanup();
    locale = 'en';
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it.each<ImportVideoResponse['status']>(['success', 'superseded'])(
    'announces a %s import, hands over the result and closes',
    async (status) => {
      const done = failure({ success: true, status, error: '', relative_path: 'videos/rick.md' });
      importVideo.mockResolvedValue(done);
      const view = renderDialog();

      await submit(view);

      await waitFor(() => expect(view.onImportFinished).toHaveBeenCalledWith(done));
      expect(importVideo).toHaveBeenCalledWith(expect.objectContaining({ url: VIDEO_URL }), undefined);
      expect(toast.success).toHaveBeenCalledWith('Video transcript ingested and enqueued for compilation');
      expect(toast.message).not.toHaveBeenCalled();
      expect(toast.error).not.toHaveBeenCalled();
      expect(view.onOpenChange).toHaveBeenCalledWith(false);
    },
  );

  it.each<MockLocale>(['en', 'zh'])(
    'says nothing new was added when the same-named source is kept in %s',
    async (lang) => {
      locale = lang;
      const kept = failure({
        success: true,
        status: 'skipped_conflict',
        error: '',
        relative_path: 'videos/rick.md',
        message: 'File already exists (skipped conflict)',
      });
      importVideo.mockResolvedValue(kept);
      const view = renderDialog();

      await submit(view);

      await waitFor(() => expect(toast.message).toHaveBeenCalledTimes(1));
      expect(toast.message).toHaveBeenCalledWith(KEPT[lang]);
      expect(toast.success).not.toHaveBeenCalled();
      expect(toast.error).not.toHaveBeenCalled();
      expect(view.onImportFinished).toHaveBeenCalledWith(kept);
      expect(view.onOpenChange).toHaveBeenCalledWith(false);
    },
  );

  describe.each<MockLocale>(['en', 'zh'])('failure reasons in %s', (lang) => {
    it.each(ERROR_CODES)('shows the sentence for %s and never the server diagnostic', async (code) => {
      locale = lang;
      importVideo.mockResolvedValue(failure({ error_code: code }));
      const view = renderDialog();

      await submit(view);

      await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
      expect(toast.error).toHaveBeenCalledWith(REASONS[lang][code]);
      expect(view.onImportFinished).not.toHaveBeenCalled();
      expect(view.onOpenChange).not.toHaveBeenCalled();
      expect(view.box.value).toBe(VIDEO_URL);
    });

    it('shows the generic sentence when the failure carries no error code', async () => {
      locale = lang;
      importVideo.mockResolvedValue(failure({ error_code: null }));
      const view = renderDialog();

      await submit(view);

      await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
      expect(toast.error).toHaveBeenCalledWith(REASONS[lang].import_failed);
    });

    it('tells a security block apart by its status and never shows the server diagnostic', async () => {
      locale = lang;
      importVideo.mockResolvedValue(
        failure({
          status: 'security_blocked',
          relative_path: 'videos/talk.md',
          error: 'Content blocked by security scanner',
        }),
      );
      const view = renderDialog();

      await submit(view);

      await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
      expect(toast.error).toHaveBeenCalledWith(BLOCKED[lang]);
      expect(view.onImportFinished).not.toHaveBeenCalled();
    });

    it('reports a request that failed outright with the generic sentence and keeps the box as it was', async () => {
      locale = lang;
      vi.spyOn(console, 'error').mockImplementation(() => {});
      importVideo.mockRejectedValue(new Error('network down'));
      const view = renderDialog();

      await submit(view);

      await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
      expect(toast.error).toHaveBeenCalledWith(REASONS[lang].import_failed);
      expect(view.onOpenChange).not.toHaveBeenCalled();
      expect(view.box.value).toBe(VIDEO_URL);
    });
  });
});
