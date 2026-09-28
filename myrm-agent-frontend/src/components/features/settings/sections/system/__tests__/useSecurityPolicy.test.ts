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
  deriveCapabilityMatrix: () => ({
    knowledge_read: 'allow',
    knowledge_write: 'ask',
    web_egress: 'allow',
    candidate_create: 'allow',
    remote_tools: 'ask',
    local_filesystem: 'ask',
  }),
  syncCapabilityActionToRules: (rules: unknown[]) => rules,
}));

const t = (key: string) => key;

async function setupHook() {
  const rendered = renderHook(() => useSecurityPolicy(t));
  await act(async () => {
    await Promise.resolve();
  });
  return rendered;
}

describe('useSecurityPolicy – command denylist toast feedback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows toast.success when adding a valid command pattern', async () => {
    const { result } = await setupHook();

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

  it('shows toast.success when removing a command pattern', async () => {
    const { result } = await setupHook();

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

  it('shows toast.error for invalid pattern (single char, no glob)', async () => {
    const { result } = await setupHook();

    act(() => {
      result.current.handleAddCommandPattern('a');
    });

    expect(toast.error).toHaveBeenCalledWith('invalidCommandPattern');
    expect(toast.success).not.toHaveBeenCalled();
    expect(mockSet).not.toHaveBeenCalled();
  });

  it('shows toast.error for duplicate pattern', async () => {
    const { result } = await setupHook();

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

  it('accepts single-char pattern with glob wildcard', async () => {
    const { result } = await setupHook();

    act(() => {
      result.current.handleAddCommandPattern('*');
    });

    expect(toast.success).toHaveBeenCalledWith('commandPatternAdded');
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('trims whitespace before processing', async () => {
    const { result } = await setupHook();

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

  it('ignores empty or whitespace-only input silently', async () => {
    const { result } = await setupHook();

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

describe('useSecurityPolicy – capability surface matrix', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('updates capability matrix and calls syncManager when surface action changes', async () => {
    const { result } = await setupHook();

    act(() => {
      result.current.handleCapabilityChange('knowledge_write', 'deny');
    });

    expect(result.current.capabilityMatrix.knowledge_write).toBe('deny');
    expect(toast.success).toHaveBeenCalledWith('capabilitySurfaceSaved');
    expect(mockSet).toHaveBeenCalledWith(
      'securityConfig',
      expect.objectContaining({
        capabilityMatrix: expect.objectContaining({
          knowledge_write: 'deny',
        }),
      }),
    );
  });

  it('applies capability preset matrix correctly', async () => {
    const { result } = await setupHook();

    const autonomousPreset = {
      knowledge_read: 'allow' as const,
      knowledge_write: 'allow' as const,
      web_egress: 'allow' as const,
      candidate_create: 'allow' as const,
      remote_tools: 'allow' as const,
      local_filesystem: 'allow' as const,
    };

    act(() => {
      result.current.handleCapabilityPresetApply(autonomousPreset);
    });

    expect(result.current.capabilityMatrix).toEqual(autonomousPreset);
    expect(toast.success).toHaveBeenCalledWith('capabilityPresetApplied');
    expect(mockSet).toHaveBeenCalledWith(
      'securityConfig',
      expect.objectContaining({
        capabilityMatrix: autonomousPreset,
      }),
    );
  });
});
