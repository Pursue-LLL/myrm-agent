import { describe, expect, it } from 'vitest';

import { selectScopedBrowserViewData, type BrowserViewData } from '@/store/useBrowserInspectorStore';

const sampleView: BrowserViewData = {
  screenshotBase64: 'abc',
  mimeType: 'image/jpeg',
  refs: {},
  pageUrl: 'https://example.com',
  pageTitle: 'Example',
  viewportWidth: 1280,
  viewportHeight: 720,
  sourceChatId: 'chat-a',
  updatedAt: 1,
};

describe('selectScopedBrowserViewData', () => {
  it('returns view data when sourceChatId matches active chat', () => {
    expect(selectScopedBrowserViewData(sampleView, 'chat-a')).toBe(sampleView);
  });

  it('returns null when sourceChatId differs from active chat', () => {
    expect(selectScopedBrowserViewData(sampleView, 'chat-b')).toBeNull();
  });

  it('returns null when chatId is missing', () => {
    expect(selectScopedBrowserViewData(sampleView, null)).toBeNull();
    expect(selectScopedBrowserViewData(sampleView, '   ')).toBeNull();
  });

  it('returns null when viewData is null', () => {
    expect(selectScopedBrowserViewData(null, 'chat-a')).toBeNull();
  });
});
