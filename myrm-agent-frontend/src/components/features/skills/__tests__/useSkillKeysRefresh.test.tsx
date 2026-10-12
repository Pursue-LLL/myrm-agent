/** @vitest-environment jsdom */

import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SkillSectionTranslator } from '../SkillDetailHelpers';
import { useLiveSkill } from '../useLiveSkill';
import { useSkillDetailSheet } from '../useSkillDetailSheet';
import { useSkillStore } from '@/store/skill';
import type { Skill } from '@/store/skill/types';

const updateSkillEnvVarsMock = vi.hoisted(() => vi.fn());
const toastMock = vi.hoisted(() => vi.fn());

vi.mock('@/services/skill', () => ({
  getSkillFile: vi.fn().mockResolvedValue(''),
  getSkillEnvVars: vi.fn().mockResolvedValue({ env_vars: {} }),
  updateSkillEnvVars: updateSkillEnvVarsMock,
  trustSkill: vi.fn(),
  untrustSkill: vi.fn(),
  toggleEvolutionLock: vi.fn(),
  revealSkill: vi.fn(),
}));

vi.mock('@/hooks/shared/useToast', () => ({ toast: toastMock }));

const t = Object.assign((key: string) => key, { has: () => true }) as unknown as SkillSectionTranslator;

function buildSkill(overrides: Partial<Skill>): Skill {
  return {
    id: 'notion-workspace',
    name: 'notion-workspace',
    description: 'Notion',
    type: 'prebuilt',
    storage_path: '/skills/notion',
    version: '1.0.0',
    category: 'office',
    icon_url: null,
    tags: [],
    is_active: true,
    requires: { bins: [], env: ['NOTION_API_KEY'], config: [] },
    available: false,
    unavailable_reason: 'Missing: ENV: NOTION_API_KEY',
    trust: 'installed',
    author: null,
    homepage: null,
    always: false,
    model_invocable: true,
    user_invocable: true,
    primary_env: null,
    security: null,
    user_trusted: false,
    evolution_locked: false,
    has_upstream_update: false,
    traps: [],
    verification_steps: [],
    eval_cases: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

const fetchMarketSkills = vi.fn().mockResolvedValue(undefined);
const fetchLocalSkills = vi.fn().mockResolvedValue(undefined);

beforeEach(() => {
  vi.clearAllMocks();
  updateSkillEnvVarsMock.mockResolvedValue(undefined);
  useSkillStore.setState({ marketSkills: [], localSkills: [], fetchMarketSkills, fetchLocalSkills });
});

function renderSheet(skill: Skill) {
  return renderHook(() => useSkillDetailSheet({ skill, open: true, isEnabled: true, onOpenChange: vi.fn(), t }));
}

describe('saving skill keys refreshes availability', () => {
  it('refetches the prebuilt list when the skill lives there', async () => {
    const skill = buildSkill({});
    useSkillStore.setState({ marketSkills: [skill] });
    const { result } = renderSheet(skill);

    await act(async () => {
      await result.current.handleSaveEnvVars();
    });

    expect(fetchMarketSkills).toHaveBeenCalledWith(true);
    expect(fetchLocalSkills).not.toHaveBeenCalled();
  });

  it('rescans local skills when the skill is not a prebuilt', async () => {
    const skill = buildSkill({ id: 'local-abc', type: 'local' });
    useSkillStore.setState({ localSkills: [skill] });
    const { result } = renderSheet(skill);

    await act(async () => {
      await result.current.handleSaveEnvVars();
    });

    expect(fetchLocalSkills).toHaveBeenCalledTimes(1);
    expect(fetchMarketSkills).not.toHaveBeenCalled();
  });

  it('does not refetch when saving fails', async () => {
    updateSkillEnvVarsMock.mockRejectedValue(new Error('boom'));
    const skill = buildSkill({});
    useSkillStore.setState({ marketSkills: [skill] });
    const { result } = renderSheet(skill);

    await act(async () => {
      await result.current.handleSaveEnvVars();
    });

    expect(fetchMarketSkills).not.toHaveBeenCalled();
    expect(fetchLocalSkills).not.toHaveBeenCalled();
  });
});

describe('useLiveSkill', () => {
  it('follows the refreshed list entry without changing the snapshot identity contract', () => {
    const snapshot = buildSkill({});
    useSkillStore.setState({ marketSkills: [snapshot] });
    const { result } = renderHook(() => useLiveSkill(snapshot));
    expect(result.current).toBe(snapshot);

    const refreshed = buildSkill({ available: true, unavailable_reason: null });
    act(() => {
      useSkillStore.setState({ marketSkills: [refreshed] });
    });

    expect(result.current).toBe(refreshed);
  });

  it('falls back to the snapshot when the skill is in no list, and passes null through', () => {
    const snapshot = buildSkill({ id: 'user-only' });

    expect(renderHook(() => useLiveSkill(snapshot)).result.current).toBe(snapshot);
    expect(renderHook(() => useLiveSkill(null)).result.current).toBeNull();
  });
});
