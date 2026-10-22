import { describe, expect, it, beforeEach } from 'vitest';
import { useVisualArtifactStudioStore } from '../useVisualArtifactStudioStore';
import { APPLE_CLEAN_SPEC } from '../designSpecParser';
import type { SelectedElementMeta } from '../designSpecTypes';

describe('useVisualArtifactStudioStore', () => {
  beforeEach(() => {
    useVisualArtifactStudioStore.getState().resetStudioState();
  });

  it('初始状态具备默认 Minimal B2B 规范且审查模式关闭', () => {
    const state = useVisualArtifactStudioStore.getState();
    expect(state.activeSpec.specId).toBe('spec_minimal_b2b');
    expect(state.isInspectMode).toBe(false);
    expect(state.selectedElement).toBeNull();
    expect(state.promptBackfillText).toBe('');
    expect(state.publicShares).toEqual([]);
  });

  it('能够切换规范并开关审查模式', () => {
    const store = useVisualArtifactStudioStore.getState();
    store.setActiveSpec(APPLE_CLEAN_SPEC);
    expect(useVisualArtifactStudioStore.getState().activeSpec.specId).toBe('spec_apple_clean');

    store.toggleInspectMode(true);
    expect(useVisualArtifactStudioStore.getState().isInspectMode).toBe(true);

    store.toggleInspectMode(false);
    expect(useVisualArtifactStudioStore.getState().isInspectMode).toBe(false);
  });

  it('选定元素时自动根据规范合成精准的微调建议 Prompt', () => {
    const store = useVisualArtifactStudioStore.getState();
    const mockElement: SelectedElementMeta = {
      selectorPath: '.hero-container > button.cta-btn',
      tagName: 'button',
      textContent: '立即免费体验',
      boundingBox: { x: 10, y: 20, width: 120, height: 40 },
      codeSnippet: '<button className="cta-btn">立即免费体验</button>',
      generatedPromptSuggestion: '调整按钮样式',
    };

    store.selectElement(mockElement);
    const updated = useVisualArtifactStudioStore.getState();
    expect(updated.selectedElement).toEqual(mockElement);
    expect(updated.promptBackfillText).toContain('.hero-container > button.cta-btn');
    expect(updated.promptBackfillText).toContain('立即免费体验');
    expect(updated.promptBackfillText).toContain('8px 圆角');

    // 清空选择
    store.clearSelection();
    expect(useVisualArtifactStudioStore.getState().selectedElement).toBeNull();
    expect(useVisualArtifactStudioStore.getState().promptBackfillText).toBe('');
  });

  it('能够生成临时公网分享短链，并支持一键撤销访问', () => {
    const store = useVisualArtifactStudioStore.getState();
    const record = store.generatePublicShare('art_test_01', 24);

    expect(record.artifactId).toBe('art_test_01');
    expect(record.publicUrl).toContain('https://share.myrm.io/s/');
    expect(record.expiresAt).not.toBeNull();
    expect(record.isRevoked).toBe(false);

    let shares = useVisualArtifactStudioStore.getState().publicShares;
    expect(shares.length).toBe(1);

    // 撤销短链
    store.revokePublicShare(record.shareId);
    shares = useVisualArtifactStudioStore.getState().publicShares;
    expect(shares[0].isRevoked).toBe(true);
  });
});
