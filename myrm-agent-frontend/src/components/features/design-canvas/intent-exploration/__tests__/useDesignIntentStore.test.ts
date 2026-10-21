import { describe, it, expect, beforeEach } from 'vitest';
import { useDesignIntentStore } from '../useDesignIntentStore';

describe('useDesignIntentStore', () => {
  beforeEach(() => {
    useDesignIntentStore.getState().reset();
  });

  it('initializes with default prompt, analyzed spec, and 3 variants', () => {
    const state = useDesignIntentStore.getState();
    expect(state.draftPrompt).toContain('咖啡店');
    expect(state.currentSpec.completenessScore).toBeGreaterThan(0);
    expect(state.variants.length).toBe(3);
    expect(state.selectedVariantId).toBe('direction-a-minimal');
    expect(state.isExplorationOpen).toBe(false);
  });

  it('updates draft prompt and triggers automatic five-element analysis', () => {
    const { setDraftPrompt } = useDesignIntentStore.getState();
    setDraftPrompt('做一张宣传海报');

    const state = useDesignIntentStore.getState();
    expect(state.draftPrompt).toBe('做一张宣传海报');
    expect(state.currentSpec.what.isDetected).toBe(true);
    expect(state.currentSpec.what.value).toBe('海报');
  });

  it('sets and clears individual element values, updating completeness score', () => {
    const { setDraftPrompt, setElementValue, clearElementValue } =
      useDesignIntentStore.getState();

    // 先设置为只包含海报（20%）
    setDraftPrompt('做一张海报');
    let state = useDesignIntentStore.getState();
    expect(state.currentSpec.completenessScore).toBe(20);

    // 手动为受众补充"年轻都市白领"
    setElementValue('audience', '年轻都市白领');
    state = useDesignIntentStore.getState();
    expect(state.currentSpec.audience.value).toBe('年轻都市白领');
    expect(state.currentSpec.audience.isDetected).toBe(true);
    // 增加了一项，完整度提升为 40%
    expect(state.currentSpec.completenessScore).toBe(40);

    // 清除受众
    clearElementValue('audience');
    state = useDesignIntentStore.getState();
    expect(state.currentSpec.audience.value).toBeNull();
    expect(state.currentSpec.audience.isDetected).toBe(false);
    expect(state.currentSpec.completenessScore).toBe(20);
  });

  it('controls active capsule key state', () => {
    const { setActiveCapsuleKey } = useDesignIntentStore.getState();

    setActiveCapsuleKey('style');
    expect(useDesignIntentStore.getState().activeCapsuleKey).toBe('style');

    setActiveCapsuleKey(null);
    expect(useDesignIntentStore.getState().activeCapsuleKey).toBeNull();
  });

  it('applies assembled prompt and replaces draftPrompt with refined commercial prompt', () => {
    const { setDraftPrompt, setElementValue, applyAssembledPrompt } =
      useDesignIntentStore.getState();

    setDraftPrompt('海报');
    setElementValue('audience', '年轻都市白领');
    setElementValue('style', '温暖复古质感');

    const refined = applyAssembledPrompt();
    expect(refined).toContain('请设计制作一份专业的【海报】');
    expect(refined).toContain('目标受众为年轻都市白领');
    expect(refined).toContain('采用温暖复古质感视觉风格');
    expect(useDesignIntentStore.getState().draftPrompt).toBe(refined);
  });

  it('generates variants and manages multi-direction exploration lifecycle', () => {
    const { generateVariants, selectVariant, closeExploration } =
      useDesignIntentStore.getState();

    generateVariants();
    let state = useDesignIntentStore.getState();
    expect(state.isExplorationOpen).toBe(true);
    expect(state.variants.length).toBe(3);

    selectVariant('direction-b-bold');
    state = useDesignIntentStore.getState();
    expect(state.selectedVariantId).toBe('direction-b-bold');

    closeExploration();
    state = useDesignIntentStore.getState();
    expect(state.isExplorationOpen).toBe(false);
  });
});
