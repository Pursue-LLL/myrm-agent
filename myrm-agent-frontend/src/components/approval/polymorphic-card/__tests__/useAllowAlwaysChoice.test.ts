import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useAllowAlwaysChoice } from '../useAllowAlwaysChoice';

const SHELL_TOOL = 'bash_code_execute_tool';
const OTHER_TOOL = 'web_search_tool';

describe('useAllowAlwaysChoice', () => {
  it('starts at the exact-command scope for a shell tool and the whole-tool scope for any other', () => {
    expect(renderHook(() => useAllowAlwaysChoice('a1', SHELL_TOOL)).result.current.scope).toBe('exact');
    expect(renderHook(() => useAllowAlwaysChoice('a1', OTHER_TOOL)).result.current.scope).toBe('tool');
  });

  it('has the tool default from the very first render', () => {
    const scopes: string[] = [];

    renderHook(() => {
      const choice = useAllowAlwaysChoice('a1', SHELL_TOOL);
      scopes.push(choice.scope);
      return choice;
    });

    expect(scopes[0]).toBe('exact');
  });

  it('starts with a session-long duration', () => {
    expect(renderHook(() => useAllowAlwaysChoice('a1', SHELL_TOOL)).result.current.duration).toBe('session');
  });

  it('keeps what the user picked while the approval and tool stay the same', () => {
    const { result, rerender } = renderHook(() => useAllowAlwaysChoice('a1', SHELL_TOOL));

    act(() => {
      result.current.setScope('pattern');
      result.current.setDuration('1h');
    });
    rerender();

    expect(result.current.scope).toBe('pattern');
    expect(result.current.duration).toBe('1h');
  });

  it('returns the scope to the tool default for the next approval but keeps the duration', () => {
    const { result, rerender } = renderHook(({ approvalId }) => useAllowAlwaysChoice(approvalId, SHELL_TOOL), {
      initialProps: { approvalId: 'a1' },
    });
    act(() => {
      result.current.setScope('permission');
      result.current.setDuration('15m');
    });

    rerender({ approvalId: 'a2' });

    expect(result.current.scope).toBe('exact');
    expect(result.current.duration).toBe('15m');
  });

  it('follows the default of a different tool', () => {
    const { result, rerender } = renderHook(({ toolName }) => useAllowAlwaysChoice('a1', toolName), {
      initialProps: { toolName: SHELL_TOOL },
    });
    expect(result.current.scope).toBe('exact');

    rerender({ toolName: OTHER_TOOL });

    expect(result.current.scope).toBe('tool');
  });
});
