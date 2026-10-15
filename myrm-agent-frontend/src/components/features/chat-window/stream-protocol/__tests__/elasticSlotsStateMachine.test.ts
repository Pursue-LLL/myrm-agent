import { describe, it, expect } from 'vitest';
import {
  createInitialViewport,
  handleUserScrollTransition,
  handleContentGrowTransition,
  handleResizeTransition,
  computeVisibleSlotsWindow,
} from '../elasticSlotsStateMachine';
import { ElasticSlotViewport } from '../streamProtocolTypes';

describe('elasticSlotsStateMachine', () => {
  it('creates initial viewport with pinned to bottom mode', () => {
    const vp = createInitialViewport();
    expect(vp.anchorMode).toBe('PINNED_BOTTOM');
    expect(vp.scrollTop).toBe(0);
    expect(vp.activeSlotIndex).toBe(0);
  });

  it('transitions to USER_DETACHED when user scrolls up', () => {
    const vp: ElasticSlotViewport = {
      scrollTop: 1000,
      scrollHeight: 1600,
      clientHeight: 600,
      anchorMode: 'PINNED_BOTTOM',
      activeSlotIndex: 20,
      totalSlotsCount: 20,
    };

    // 用户向上滚到 500 (此时距底部 = 1600 - (500 + 600) = 500px > 32px)
    const { nextViewport, modeChanged } = handleUserScrollTransition(vp, 500);
    expect(nextViewport.anchorMode).toBe('USER_DETACHED');
    expect(nextViewport.scrollTop).toBe(500);
    expect(modeChanged).toBe(true);

    // 用户滚回底部附近 980 (此时距底部 = 1600 - (980 + 600) = 20px <= 32px)
    const backResult = handleUserScrollTransition(nextViewport, 980);
    expect(backResult.nextViewport.anchorMode).toBe('PINNED_BOTTOM');
    expect(backResult.modeChanged).toBe(true);
  });

  it('keeps viewport anchored to bottom on content grow when PINNED_BOTTOM', () => {
    const vp: ElasticSlotViewport = {
      scrollTop: 400,
      scrollHeight: 1000,
      clientHeight: 600,
      anchorMode: 'PINNED_BOTTOM',
      activeSlotIndex: 10,
      totalSlotsCount: 10,
    };

    // 新增内容，总高度变为 1500
    const { nextViewport, targetScrollTop } = handleContentGrowTransition(vp, 1500, 15);
    expect(targetScrollTop).toBe(900); // 1500 - 600 = 900
    expect(nextViewport.scrollTop).toBe(900);
    expect(nextViewport.totalSlotsCount).toBe(15);
  });

  it('preserves user scroll position on content grow when USER_DETACHED', () => {
    const vp: ElasticSlotViewport = {
      scrollTop: 300,
      scrollHeight: 1000,
      clientHeight: 600,
      anchorMode: 'USER_DETACHED',
      activeSlotIndex: 5,
      totalSlotsCount: 10,
    };

    // 内容增加至 2000，但由于用户正在阅读历史，scrollTop 保持 300
    const { nextViewport, targetScrollTop } = handleContentGrowTransition(vp, 2000, 20);
    expect(targetScrollTop).toBe(300);
    expect(nextViewport.scrollTop).toBe(300);
    expect(nextViewport.anchorMode).toBe('USER_DETACHED');
  });

  it('re-anchors viewport accurately on window resize', () => {
    const vp: ElasticSlotViewport = {
      scrollTop: 1000,
      scrollHeight: 1600,
      clientHeight: 600,
      anchorMode: 'PINNED_BOTTOM',
      activeSlotIndex: 15,
      totalSlotsCount: 15,
    };

    // 窗口高度扩大到 800
    const { nextViewport, reanchoredScrollTop } = handleResizeTransition(vp, 800);
    expect(reanchoredScrollTop).toBe(800); // 1600 - 800 = 800
    expect(nextViewport.clientHeight).toBe(800);
  });

  it('computes virtual visible slots window with overscan protection', () => {
    const windowSlots = computeVisibleSlotsWindow(200, 400, 100, 50, 2);
    // rawStart = 200 / 50 = 4, rawEnd = 600 / 50 = 12
    // with overscan=2: start = 4-2=2, end = 12+2=14
    expect(windowSlots.startIndex).toBe(2);
    expect(windowSlots.endIndex).toBe(14);

    const emptySlots = computeVisibleSlotsWindow(0, 400, 0);
    expect(emptySlots.startIndex).toBe(0);
    expect(emptySlots.endIndex).toBe(0);
  });
});
