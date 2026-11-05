import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { MockLocale } from '@/test-utils/realIntl';
import useChatStore from '@/store/useChatStore';

import { useActiveComposerOptions } from '../useActiveComposerOptions';

let locale: MockLocale = 'zh';
vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => locale));

const NOTHING_ON = {
  actionMode: 'agent',
  searchDepth: 'normal',
  isWorkflowMode: false,
  isGoalMode: false,
  incognitoMode: false,
} as const;

describe('the sentence naming the modes that are on', () => {
  beforeEach(() => {
    locale = 'zh';
    useChatStore.setState(NOTHING_ON);
  });

  it('is empty while no mode is on', () => {
    const { result } = renderHook(() => useActiveComposerOptions());

    expect(result.current).toBeNull();
  });

  it('names deep search beside the fast mode', () => {
    useChatStore.setState({ actionMode: 'fast', searchDepth: 'deep' });
    const { result } = renderHook(() => useActiveComposerOptions());

    expect(result.current).toBe('已启用：深度搜索');
  });

  it('does not announce a deep-search value that the agent mode leaves behind', () => {
    useChatStore.setState({ actionMode: 'agent', searchDepth: 'deep' });
    const { result } = renderHook(() => useActiveComposerOptions());

    expect(result.current).toBeNull();
  });

  it('names a goal only beside the agent mode', () => {
    useChatStore.setState({ actionMode: 'agent', isGoalMode: true });
    const { result } = renderHook(() => useActiveComposerOptions());
    expect(result.current).toBe('已启用：作为长期目标执行');

    act(() => useChatStore.setState({ actionMode: 'fast' }));
    expect(result.current).toBeNull();
  });

  it('lists every mode that is on, in a fixed order, in the viewer language', () => {
    useChatStore.setState({ isWorkflowMode: true, incognitoMode: true, isGoalMode: true });
    const { result, rerender } = renderHook(() => useActiveComposerOptions());
    expect(result.current).toBe('已启用：编排模式 (PTC)、作为长期目标执行、无痕模式');

    locale = 'en';
    rerender();
    expect(result.current).toMatch(/^On: .+, .+, .+$/);
  });

  it('follows the store as modes are switched', () => {
    const { result } = renderHook(() => useActiveComposerOptions());

    act(() => useChatStore.setState({ incognitoMode: true }));
    expect(result.current).toBe('已启用：无痕模式');

    act(() => useChatStore.setState({ incognitoMode: false }));
    expect(result.current).toBeNull();
  });
});
