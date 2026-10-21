import { ElasticSlotViewport, ViewportAnchorMode } from './streamProtocolTypes';

const PIN_BOTTOM_THRESHOLD_PX = 32;

export function createInitialViewport(): ElasticSlotViewport {
  return {
    scrollTop: 0,
    scrollHeight: 0,
    clientHeight: 600,
    anchorMode: 'PINNED_BOTTOM',
    activeSlotIndex: 0,
    totalSlotsCount: 0,
  };
}

export function handleUserScrollTransition(
  viewport: ElasticSlotViewport,
  newScrollTop: number
): {
  nextViewport: ElasticSlotViewport;
  modeChanged: boolean;
} {
  const distanceFromBottom = viewport.scrollHeight - (newScrollTop + viewport.clientHeight);
  const nextMode: ViewportAnchorMode =
    distanceFromBottom > PIN_BOTTOM_THRESHOLD_PX ? 'USER_DETACHED' : 'PINNED_BOTTOM';

  const modeChanged = nextMode !== viewport.anchorMode;

  return {
    nextViewport: {
      ...viewport,
      scrollTop: Math.max(0, newScrollTop),
      anchorMode: nextMode,
    },
    modeChanged,
  };
}

export function handleContentGrowTransition(
  viewport: ElasticSlotViewport,
  newScrollHeight: number,
  newSlotsCount: number
): {
  nextViewport: ElasticSlotViewport;
  targetScrollTop: number;
} {
  let targetScrollTop = viewport.scrollTop;

  // TLA+ 契约: 当且仅当处于 PINNED_BOTTOM 时，自动锚定随内容增长推入底部
  if (viewport.anchorMode === 'PINNED_BOTTOM') {
    targetScrollTop = Math.max(0, newScrollHeight - viewport.clientHeight);
  }

  return {
    nextViewport: {
      ...viewport,
      scrollHeight: newScrollHeight,
      scrollTop: targetScrollTop,
      totalSlotsCount: newSlotsCount,
      activeSlotIndex: Math.max(0, newSlotsCount - 1),
    },
    targetScrollTop,
  };
}

export function handleResizeTransition(
  viewport: ElasticSlotViewport,
  newClientHeight: number
): {
  nextViewport: ElasticSlotViewport;
  reanchoredScrollTop: number;
} {
  let reanchoredScrollTop = viewport.scrollTop;
  if (viewport.anchorMode === 'PINNED_BOTTOM') {
    reanchoredScrollTop = Math.max(0, viewport.scrollHeight - newClientHeight);
  } else {
    // 防止视口越界
    reanchoredScrollTop = Math.min(
      viewport.scrollTop,
      Math.max(0, viewport.scrollHeight - newClientHeight)
    );
  }

  return {
    nextViewport: {
      ...viewport,
      clientHeight: newClientHeight,
      scrollTop: reanchoredScrollTop,
    },
    reanchoredScrollTop,
  };
}

export function computeVisibleSlotsWindow(
  scrollTop: number,
  clientHeight: number,
  totalSlots: number,
  estimatedSlotHeight: number = 48,
  overscan: number = 4
): {
  startIndex: number;
  endIndex: number;
} {
  if (totalSlots <= 0) {
    return { startIndex: 0, endIndex: 0 };
  }

  const rawStart = Math.floor(scrollTop / estimatedSlotHeight);
  const rawEnd = Math.ceil((scrollTop + clientHeight) / estimatedSlotHeight);

  const startIndex = Math.max(0, rawStart - overscan);
  const endIndex = Math.min(totalSlots - 1, rawEnd + overscan);

  return {
    startIndex,
    endIndex,
  };
}
