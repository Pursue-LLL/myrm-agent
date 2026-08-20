import { describe, expect, it } from 'vitest';

import { selectScopedDesktopViewData, type DesktopViewData } from '@/store/useDesktopInspectorStore';

const sampleView: DesktopViewData = {
  screenshotBase64: 'abc',
  mimeType: 'image/jpeg',
  refs: {},
  appName: 'TextEdit',
  windowTitle: 'Untitled',
  scope: 'app',
  needsPermission: false,
  viewportWidth: 1280,
  viewportHeight: 720,
  sourceChatId: 'chat-a',
  updatedAt: 1,
};

describe('selectScopedDesktopViewData', () => {
  it('returns view data when sourceChatId matches active chat', () => {
    expect(selectScopedDesktopViewData(sampleView, 'chat-a')).toBe(sampleView);
  });

  it('returns null when sourceChatId differs from active chat', () => {
    expect(selectScopedDesktopViewData(sampleView, 'chat-b')).toBeNull();
  });

  it('returns null when chatId is missing', () => {
    expect(selectScopedDesktopViewData(sampleView, null)).toBeNull();
    expect(selectScopedDesktopViewData(sampleView, '   ')).toBeNull();
  });

  it('returns null when viewData is null', () => {
    expect(selectScopedDesktopViewData(null, 'chat-a')).toBeNull();
  });
});
