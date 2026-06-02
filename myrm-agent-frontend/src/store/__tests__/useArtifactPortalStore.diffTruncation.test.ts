/**
 * [INPUT]
 * `@/store/useArtifactPortalStore`（POS: Portal 标签、`diffPreviewTruncated`、`updateTabContent`）；
 * `@/store/chat/types`::Artifact（POS: 工件领域类型）。
 * [OUTPUT]
 * Vitest：`openArtifact` / `updateTabContent` 在截断语义下的一致性断言。
 * [POS]
 * Artifact Diff 截断标志的回归守门；与 `FILE_DIFF → updateTabContent(..., { truncated })` 契约对齐。
 */

import { beforeEach, describe, expect, it } from 'vitest';

import useArtifactPortalStore from '@/store/useArtifactPortalStore';
import type { Artifact } from '@/store/chat/types';

function minimalArtifact(id: string, overrides: Partial<Artifact> = {}): Artifact {
  return {
    id,
    filename: 'a.txt',
    type: 'code',
    content_type: 'text/plain',
    size: 0,
    preview_url: '',
    download_url: '',
    language: 'diff',
    ...overrides,
  };
}

describe('useArtifactPortalStore — diff truncation flag', () => {
  beforeEach(() => {
    useArtifactPortalStore.getState().closeAllTabs();
  });

  it('sets diffPreviewTruncated when openArtifact receives diffPreviewTruncated: true', () => {
    const art = minimalArtifact('diff-tab-1');
    useArtifactPortalStore.getState().setCachedContent(art.id, '--- a/foo');
    useArtifactPortalStore.getState().openArtifact(art, { diffPreviewTruncated: true });

    const tabs = useArtifactPortalStore.getState().openTabs;
    expect(tabs).toHaveLength(1);
    expect(tabs[0].diffPreviewTruncated).toBe(true);
  });

  it('defaults diffPreviewTruncated to false when options omit the flag', () => {
    const art = minimalArtifact('diff-tab-2');
    useArtifactPortalStore.getState().openArtifact(art);

    expect(useArtifactPortalStore.getState().openTabs[0].diffPreviewTruncated).toBe(false);
  });

  it('updates diffPreviewTruncated when reopening existing tab with explicit options', () => {
    const art = minimalArtifact('diff-tab-3');
    useArtifactPortalStore.getState().openArtifact(art);
    expect(useArtifactPortalStore.getState().openTabs[0].diffPreviewTruncated).toBe(false);

    useArtifactPortalStore.getState().openArtifact(art, { diffPreviewTruncated: true });
    expect(useArtifactPortalStore.getState().openTabs[0].diffPreviewTruncated).toBe(true);

    useArtifactPortalStore.getState().openArtifact(art, { diffPreviewTruncated: false });
    expect(useArtifactPortalStore.getState().openTabs[0].diffPreviewTruncated).toBe(false);
  });

  it('merge: updateTabContent(..., { truncated: true }) sets diffPreviewTruncated', () => {
    const art = minimalArtifact('stream-diff-1');
    useArtifactPortalStore.getState().setCachedContent(art.id, '');
    useArtifactPortalStore.getState().openArtifact(art);

    useArtifactPortalStore.getState().updateTabContent(art.id, '+added line\n', {
      truncated: true,
    });

    const tabs = useArtifactPortalStore.getState().openTabs;
    expect(tabs[0].content).toBe('+added line\n');
    expect(tabs[0].diffPreviewTruncated).toBe(true);
  });
});
