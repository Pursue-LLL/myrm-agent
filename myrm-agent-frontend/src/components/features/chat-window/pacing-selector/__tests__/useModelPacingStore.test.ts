import { describe, it, expect, beforeEach } from 'vitest';
import { act } from '@testing-library/react';
import useChatStore from '@/store/useChatStore';
import { useModelPacingStore } from '../useModelPacingStore';

describe('useModelPacingStore', () => {
  beforeEach(() => {
    act(() => {
      useChatStore.setState({
        optimizationMode: 'speed',
      });
      useModelPacingStore.getState().resetStore();
    });
  });

  it('initializes with default balanced pacing tier', () => {
    const state = useModelPacingStore.getState();
    expect(state.activeTier).toBe('balanced');
    expect(state.isPopoverOpen).toBe(false);
    expect(state.perChatOverrides).toEqual({});
  });

  it('sets pacing tier and synchronizes with useChatStore optimizationMode', () => {
    act(() => {
      useModelPacingStore.getState().setPacingTier('fast');
    });

    expect(useModelPacingStore.getState().activeTier).toBe('fast');
    expect(useChatStore.getState().optimizationMode).toBe('speed');

    act(() => {
      useModelPacingStore.getState().setPacingTier('smart');
    });

    expect(useModelPacingStore.getState().activeTier).toBe('smart');
    expect(useChatStore.getState().optimizationMode).toBe('quality');
  });

  it('records per-chat override when chatId is provided', () => {
    act(() => {
      useModelPacingStore.getState().setPacingTier('smart', 'chat_arch_review');
    });

    const state = useModelPacingStore.getState();
    expect(state.perChatOverrides['chat_arch_review']).toBe('smart');

    // Switch to another tier globally
    act(() => {
      useModelPacingStore.getState().setPacingTier('fast');
    });
    expect(useModelPacingStore.getState().activeTier).toBe('fast');

    // Load back override
    act(() => {
      useModelPacingStore.getState().loadChatOverride('chat_arch_review');
    });
    expect(useModelPacingStore.getState().activeTier).toBe('smart');
  });

  it('toggles popover visibility state', () => {
    expect(useModelPacingStore.getState().isPopoverOpen).toBe(false);

    act(() => {
      useModelPacingStore.getState().togglePopover();
    });
    expect(useModelPacingStore.getState().isPopoverOpen).toBe(true);

    act(() => {
      useModelPacingStore.getState().togglePopover(false);
    });
    expect(useModelPacingStore.getState().isPopoverOpen).toBe(false);
  });

  it('resets store properly', () => {
    act(() => {
      useModelPacingStore.getState().setPacingTier('smart', 'chat_1');
      useModelPacingStore.getState().togglePopover(true);
    });

    act(() => {
      useModelPacingStore.getState().resetStore();
    });

    const state = useModelPacingStore.getState();
    expect(state.activeTier).toBe('balanced');
    expect(state.isPopoverOpen).toBe(false);
    expect(state.perChatOverrides).toEqual({});
  });
});
