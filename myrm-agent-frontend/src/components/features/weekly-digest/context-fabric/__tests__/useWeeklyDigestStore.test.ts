import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useWeeklyDigestStore } from '../useWeeklyDigestStore';
import { INITIAL_CHANNEL_FOOTPRINTS } from '../footprintAggregatorData';

describe('useWeeklyDigestStore', () => {
  beforeEach(() => {
    useWeeklyDigestStore.getState().resetState();
  });

  it('initializes with default footprints, week identifier and filters', () => {
    const state = useWeeklyDigestStore.getState();
    expect(state.footprints.length).toBe(INITIAL_CHANNEL_FOOTPRINTS.length);
    expect(state.selectedChannelFilter).toBe('all');
    expect(state.selectedCategoryFilter).toBe('all');
    expect(state.selectedWeekIdentifier).toBe('2026-W36');
    expect(state.activeStylePreset).toBe('executive');
    expect(state.isSynthesizerModalOpen).toBe(false);
    expect(state.currentDigest).toBeNull();
  });

  it('updates channel and category filters correctly', () => {
    const store = useWeeklyDigestStore.getState();

    store.setChannelFilter('feishu');
    expect(useWeeklyDigestStore.getState().selectedChannelFilter).toBe('feishu');

    store.setCategoryFilter('deliverable');
    expect(useWeeklyDigestStore.getState().selectedCategoryFilter).toBe('deliverable');
  });

  it('toggles footprint inclusion and sets all inclusions', () => {
    const store = useWeeklyDigestStore.getState();
    const firstId = INITIAL_CHANNEL_FOOTPRINTS[0].id;

    store.toggleFootprintIncluded(firstId);
    expect(
      useWeeklyDigestStore.getState().footprints.find((f) => f.id === firstId)
        ?.includedInDigest
    ).toBe(false);

    store.setAllFootprintsIncluded(false);
    expect(
      useWeeklyDigestStore
        .getState()
        .footprints.every((f) => !f.includedInDigest)
    ).toBe(true);

    store.setAllFootprintsIncluded(true);
    expect(
      useWeeklyDigestStore
        .getState()
        .footprints.every((f) => f.includedInDigest)
    ).toBe(true);
  });

  it('adds a new footprint item to the store', () => {
    const store = useWeeklyDigestStore.getState();

    store.addFootprintItem({
      channel: 'cli',
      category: 'learning',
      title: '新探索：WebAssembly SIMD 加速矩阵运算',
      description: '实测提升 2.4 倍吞吐量',
    });

    const state = useWeeklyDigestStore.getState();
    expect(state.footprints.length).toBe(INITIAL_CHANNEL_FOOTPRINTS.length + 1);
    expect(state.footprints[0].title).toBe('新探索：WebAssembly SIMD 加速矩阵运算');
    expect(state.footprints[0].includedInDigest).toBe(true);
  });

  it('opens and closes synthesizer modal, auto-synthesizing if null', () => {
    const store = useWeeklyDigestStore.getState();

    store.openSynthesizerModal();
    const openState = useWeeklyDigestStore.getState();
    expect(openState.isSynthesizerModalOpen).toBe(true);
    expect(openState.currentDigest).not.toBeNull();
    expect(openState.currentDigest?.weekIdentifier).toBe('2026-W36');

    store.closeSynthesizerModal();
    expect(useWeeklyDigestStore.getState().isSynthesizerModalOpen).toBe(false);
  });

  it('synthesizes digest with specified style preset', async () => {
    const store = useWeeklyDigestStore.getState();

    await store.synthesizeDigest('technical');
    const state = useWeeklyDigestStore.getState();

    expect(state.activeStylePreset).toBe('technical');
    expect(state.currentDigest?.stylePreset).toBe('technical');
    expect(state.currentDigest?.markdownContent).toContain('研发工作周报');
    expect(state.isSynthesizing).toBe(false);
  });

  it('refines digest through natural language instructions', async () => {
    const store = useWeeklyDigestStore.getState();
    await store.synthesizeDigest('executive');

    await store.refineDigest('改为极简速览格式');
    const refinedState = useWeeklyDigestStore.getState();

    expect(refinedState.activeStylePreset).toBe('bullet');
    expect(refinedState.refinementInstructions.length).toBe(1);
    expect(refinedState.refinementInstructions[0].prompt).toBe('改为极简速览格式');
  });

  it('handles export of digest and dispatches custom event', async () => {
    const store = useWeeklyDigestStore.getState();
    await store.synthesizeDigest('executive');

    const eventSpy = vi.fn();
    window.addEventListener('myrm:weekly-digest-exported', eventSpy);

    const successFeishu = await store.exportDigest('feishu');
    expect(successFeishu).toBe(true);
    expect(useWeeklyDigestStore.getState().lastExportStatus?.target).toBe('feishu');
    expect(eventSpy).toHaveBeenCalledTimes(1);

    window.removeEventListener('myrm:weekly-digest-exported', eventSpy);
  });
});
