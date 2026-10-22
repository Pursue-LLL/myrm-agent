import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { usePermissionAutoApprove } from '../usePermissionAutoApprove';
import { usePermissionTierStore } from '../usePermissionTierStore';

describe('usePermissionAutoApprove', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    usePermissionTierStore.setState({ tier: 'strict' });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('does not auto-approve in strict mode', () => {
    const onApprove = vi.fn();
    const { result } = renderHook(() =>
      usePermissionAutoApprove({
        toolName: 'write_to_file',
        toolInput: { TargetFile: '/src/app.ts' },
        onApprove,
        autoApproveDelayMs: 200,
      }),
    );

    expect(result.current.tier).toBe('strict');
    expect(result.current.isAutoApproved).toBe(false);
    expect(result.current.isHighRiskIntercepted).toBe(false);

    vi.advanceTimersByTime(500);
    expect(onApprove).not.toHaveBeenCalled();
  });

  it('triggers onApprove after delay for code-safe operations in semi-auto mode', () => {
    usePermissionTierStore.setState({ tier: 'semi-auto' });
    const onApprove = vi.fn();

    const { result } = renderHook(() =>
      usePermissionAutoApprove({
        toolName: 'replace_file_content',
        toolInput: { TargetFile: '/src/app.ts' },
        onApprove,
        autoApproveDelayMs: 200,
      }),
    );

    expect(result.current.tier).toBe('semi-auto');
    expect(result.current.isAutoApproved).toBe(true);
    expect(result.current.isHighRiskIntercepted).toBe(false);

    vi.advanceTimersByTime(250);
    expect(onApprove).toHaveBeenCalledTimes(1);
  });

  it('flags high-risk command and prevents auto-approval in semi-auto mode', () => {
    usePermissionTierStore.setState({ tier: 'semi-auto' });
    const onApprove = vi.fn();

    const { result } = renderHook(() =>
      usePermissionAutoApprove({
        toolName: 'run_command',
        toolInput: { command: 'rm -rf /workspace' },
        onApprove,
        autoApproveDelayMs: 200,
      }),
    );

    expect(result.current.tier).toBe('semi-auto');
    expect(result.current.isAutoApproved).toBe(false);
    expect(result.current.isHighRiskIntercepted).toBe(true);

    vi.advanceTimersByTime(500);
    expect(onApprove).not.toHaveBeenCalled();
  });
});
