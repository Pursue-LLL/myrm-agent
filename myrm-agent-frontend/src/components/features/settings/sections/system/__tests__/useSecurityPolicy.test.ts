import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useSecurityPolicy } from '../useSecurityPolicy';
import { toast } from '@/lib/utils/toast';

const { mockSet, mockGet, mockSubscribe } = vi.hoisted(() => ({
  mockSet: vi.fn(),
  mockGet: vi.fn(() => Promise.resolve(null)),
  mockSubscribe: vi.fn(() => () => {}),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

vi.mock('@/services/config', () => ({
  getConfigSyncManager: () => ({
    set: mockSet,
    get: mockGet,
    subscribe: mockSubscribe,
  }),
}));

vi.mock('@/store/useProviderStore', () => ({
  default: () => ({
    providers: {},
    getEnabledModels: () => [],
  }),
}));

vi.mock('../securityPolicyUtils', () => ({
  flattenPermissions: () => [],
  buildPermissions: () => ({}),
  DEFAULT_CONFIG: { approvalTimeoutSeconds: 120 },
  createEmptyRule: () => ({ pattern: '', action: 'ask' }),
  DOMAIN_PATTERN: /^(\*\.)?[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$/i,
}));

const t = (key: string) => key;

describe('useSecurityPolicy – command denylist toast feedback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows toast.success when adding a valid command pattern', () => {
    const { result } = renderHook(() => useSecurityPolicy(t));

    act(() => {
      result.current.handleAddCommandPattern('git push --force*');
    });

    expect(toast.success).toHaveBeenCalledWith('commandPatternAdded');
    expect(mockSet).toHaveBeenCalledWith(
      'securityConfig',
      expect.objectContaining({
        commandDenylist: ['git push --force*'],
      }),
    );
  });

  it('shows toast.success when removing a command pattern', () => {
    const { result } = renderHook(() => useSecurityPolicy(t));

    act(() => {
      result.current.handleAddCommandPattern('*DROP DATABASE*');
    });
    vi.clearAllMocks();

    act(() => {
      result.current.handleRemoveCommandPattern(0);
    });

    expect(toast.success).toHaveBeenCalledWith('commandPatternRemoved');
    expect(mockSet).toHaveBeenCalledWith(
      'securityConfig',
      expect.objectContaining({
        commandDenylist: [],
      }),
    );
  });

  it('shows toast.error for invalid pattern (single char, no glob)', () => {
    const { result } = renderHook(() => useSecurityPolicy(t));

    act(() => {
      result.current.handleAddCommandPattern('a');
    });

    expect(toast.error).toHaveBeenCalledWith('invalidCommandPattern');
    expect(toast.success).not.toHaveBeenCalled();
    expect(mockSet).not.toHaveBeenCalled();
  });

  it('shows toast.error for duplicate pattern', () => {
    const { result } = renderHook(() => useSecurityPolicy(t));

    act(() => {
      result.current.handleAddCommandPattern('rm -rf*');
    });
    vi.clearAllMocks();

    act(() => {
      result.current.handleAddCommandPattern('rm -rf*');
    });

    expect(toast.error).toHaveBeenCalledWith('duplicateCommandPattern');
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('accepts single-char pattern with glob wildcard', () => {
    const { result } = renderHook(() => useSecurityPolicy(t));

    act(() => {
      result.current.handleAddCommandPattern('*');
    });

    expect(toast.success).toHaveBeenCalledWith('commandPatternAdded');
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('trims whitespace before processing', () => {
    const { result } = renderHook(() => useSecurityPolicy(t));

    act(() => {
      result.current.handleAddCommandPattern('  git push --force*  ');
    });

    expect(toast.success).toHaveBeenCalledWith('commandPatternAdded');
    expect(mockSet).toHaveBeenCalledWith(
      'securityConfig',
      expect.objectContaining({
        commandDenylist: ['git push --force*'],
      }),
    );
  });

  it('ignores empty or whitespace-only input silently', () => {
    const { result } = renderHook(() => useSecurityPolicy(t));

    act(() => {
      result.current.handleAddCommandPattern('');
    });
    act(() => {
      result.current.handleAddCommandPattern('   ');
    });

    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
    expect(mockSet).not.toHaveBeenCalled();
  });
});
