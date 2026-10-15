import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useModelSpotlightStore } from '../useModelSpotlightStore';
import { SPOTLIGHT_CATALOG } from '../spotlightCatalogData';

describe('useModelSpotlightStore', () => {
  beforeEach(() => {
    useModelSpotlightStore.getState().restoreDismissedSpotlights();
    useModelSpotlightStore.getState().closePlayground();
    useModelSpotlightStore.getState().closeMountModal();
    useModelSpotlightStore.getState().clearPlayground();
    useModelSpotlightStore.getState().setCurrentAgentModelId('openai/gpt-4o');
  });

  it('initializes with default catalog and active spotlight', () => {
    const state = useModelSpotlightStore.getState();
    expect(state.catalog.length).toBeGreaterThan(0);
    expect(state.activeSpotlightId).toBe(SPOTLIGHT_CATALOG[0].id);
    expect(state.isBannerCollapsed).toBe(false);
    expect(state.isPlaygroundOpen).toBe(false);
    expect(state.isMountModalOpen).toBe(false);
  });

  it('switches active spotlight and toggles banner collapse', () => {
    const store = useModelSpotlightStore.getState();
    const secondId = SPOTLIGHT_CATALOG[1].id;

    store.setActiveSpotlight(secondId);
    expect(useModelSpotlightStore.getState().activeSpotlightId).toBe(secondId);

    store.toggleBannerCollapsed();
    expect(useModelSpotlightStore.getState().isBannerCollapsed).toBe(true);

    store.toggleBannerCollapsed();
    expect(useModelSpotlightStore.getState().isBannerCollapsed).toBe(false);
  });

  it('dismisses spotlight and restores dismissed spotlights', () => {
    const store = useModelSpotlightStore.getState();
    const firstId = SPOTLIGHT_CATALOG[0].id;

    store.dismissSpotlight(firstId, true);
    const dismissedState = useModelSpotlightStore.getState();

    expect(dismissedState.dismissedRecords[firstId]).toBeDefined();
    expect(dismissedState.dismissedRecords[firstId].permanent).toBe(true);
    expect(dismissedState.activeSpotlightId).toBe(SPOTLIGHT_CATALOG[1].id);

    store.restoreDismissedSpotlights();
    const restoredState = useModelSpotlightStore.getState();
    expect(Object.keys(restoredState.dismissedRecords).length).toBe(0);
    expect(restoredState.activeSpotlightId).toBe(SPOTLIGHT_CATALOG[0].id);
  });

  it('manages playground lifecycle and message dispatch', async () => {
    const store = useModelSpotlightStore.getState();
    const target = SPOTLIGHT_CATALOG[0];

    store.openPlayground(target);
    expect(useModelSpotlightStore.getState().isPlaygroundOpen).toBe(true);
    expect(useModelSpotlightStore.getState().playgroundSpotlight?.id).toBe(target.id);
    expect(useModelSpotlightStore.getState().playgroundMessages.length).toBe(1);

    await store.sendPlaygroundPrompt('如何优化分布式缓存？');
    const stateAfterPrompt = useModelSpotlightStore.getState();
    expect(stateAfterPrompt.playgroundMessages.length).toBe(3); // system, user, assistant
    expect(stateAfterPrompt.playgroundMessages[1].role).toBe('user');
    expect(stateAfterPrompt.playgroundMessages[2].role).toBe('assistant');
    expect(stateAfterPrompt.isPlaygroundThinking).toBe(false);

    store.clearPlayground();
    expect(useModelSpotlightStore.getState().playgroundMessages.length).toBe(0);

    store.closePlayground();
    expect(useModelSpotlightStore.getState().isPlaygroundOpen).toBe(false);
  });

  it('ignores empty prompts in playground', async () => {
    const store = useModelSpotlightStore.getState();
    const target = SPOTLIGHT_CATALOG[0];
    store.openPlayground(target);

    await store.sendPlaygroundPrompt('   ');
    expect(useModelSpotlightStore.getState().playgroundMessages.length).toBe(1);
  });

  it('manages mount modal and dispatches global event on confirmation', () => {
    const store = useModelSpotlightStore.getState();
    const target = SPOTLIGHT_CATALOG[0];
    const eventSpy = vi.fn();

    window.addEventListener('myrm:model-hot-mounted', eventSpy);

    store.openMountModal(target);
    expect(useModelSpotlightStore.getState().isMountModalOpen).toBe(true);
    expect(useModelSpotlightStore.getState().mountTargetSpotlight?.id).toBe(target.id);

    store.confirmMountModel(target);

    const stateAfterMount = useModelSpotlightStore.getState();
    expect(stateAfterMount.isMountModalOpen).toBe(false);
    expect(stateAfterMount.currentAgentModelId).toBe(target.modelId);
    expect(stateAfterMount.lastMountedModelId).toBe(target.modelId);
    expect(eventSpy).toHaveBeenCalledTimes(1);

    window.removeEventListener('myrm:model-hot-mounted', eventSpy);
  });

  it('closes mount modal properly without mounting', () => {
    const store = useModelSpotlightStore.getState();
    store.openMountModal(SPOTLIGHT_CATALOG[1]);
    expect(useModelSpotlightStore.getState().isMountModalOpen).toBe(true);

    store.closeMountModal();
    expect(useModelSpotlightStore.getState().isMountModalOpen).toBe(false);
    expect(useModelSpotlightStore.getState().mountTargetSpotlight).toBeNull();
  });
});
