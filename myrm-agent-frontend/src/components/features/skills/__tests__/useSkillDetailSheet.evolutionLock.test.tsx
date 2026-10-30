/**
 * Regression tests for the evolution lock toggle in the skill detail sheet: a successful toggle lands in the skill
 * store, so the skill reopens in the state the user just chose; a refused toggle leaves store and sheet untouched.
 */
/** @vitest-environment jsdom */

import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SkillSectionTranslator } from '../SkillDetailHelpers';
import { useLiveSkill } from '../useLiveSkill';
import { useSkillDetailSheet } from '../useSkillDetailSheet';
import { useSkillStore } from '@/store/skill';
import type { Skill } from '@/store/skill/types';

const { toggleEvolutionLockMock, getSkillFileMock, toastMock } = vi.hoisted(() => ({
  toggleEvolutionLockMock: vi.fn(),
  getSkillFileMock: vi.fn(),
  toastMock: vi.fn(),
}));

vi.mock('@/services/skill', () => ({
  getSkillFile: getSkillFileMock,
  getSkillEnvVars: vi.fn().mockResolvedValue({ env_vars: {} }),
  updateSkillEnvVars: vi.fn(),
  trustSkill: vi.fn(),
  untrustSkill: vi.fn(),
  toggleEvolutionLock: toggleEvolutionLockMock,
  revealSkill: vi.fn(),
}));

vi.mock('@/hooks/shared/useToast', () => ({ toast: toastMock }));

const t = Object.assign((key: string) => key, { has: () => true }) as unknown as SkillSectionTranslator;

function buildLocalSkill(id: string, locked: boolean): Skill {
  return {
    id,
    name: id,
    type: 'local',
    evolution_locked: locked,
    requires: { bins: [], env: [], config: [] },
  } as unknown as Skill;
}

function storedLocalSkill(id: string): Skill {
  const skill = useSkillStore.getState().localSkills.find((candidate) => candidate.id === id);
  if (!skill) {
    throw new Error(`skill ${id} is not in the store`);
  }
  return skill;
}

/** Mirrors SkillDetailSheet: the sheet's effects key off the opened snapshot, its display follows the store. */
function renderSheet(initial: Skill) {
  return renderHook(
    ({ snapshot, open }: { snapshot: Skill; open: boolean }) => ({
      sheet: useSkillDetailSheet({ skill: snapshot, open, isEnabled: true, onOpenChange: vi.fn(), t }),
      live: useLiveSkill(snapshot),
    }),
    { initialProps: { snapshot: initial, open: true } },
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  getSkillFileMock.mockResolvedValue('');
  toggleEvolutionLockMock.mockResolvedValue(undefined);
  useSkillStore.setState({
    localSkills: [buildLocalSkill('local::alpha', true), buildLocalSkill('local::beta', true)],
    marketSkills: [],
  });
});

describe('toggling the evolution lock from the skill detail sheet', () => {
  it('reopens unlocked after unlocking, and leaves other skills and the opened SKILL.md alone', async () => {
    const { result, rerender } = renderSheet(storedLocalSkill('local::alpha'));
    await act(async () => {});
    expect(result.current.sheet.isEvolutionLocked).toBe(true);
    expect(getSkillFileMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.sheet.handleToggleEvolutionLock();
    });

    expect(toggleEvolutionLockMock).toHaveBeenCalledWith('local::alpha', false);
    expect(result.current.sheet.isEvolutionLocked).toBe(false);
    expect(result.current.live?.evolution_locked).toBe(false);
    expect(storedLocalSkill('local::beta').evolution_locked).toBe(true);
    expect(getSkillFileMock).toHaveBeenCalledTimes(1);

    rerender({ snapshot: storedLocalSkill('local::alpha'), open: false });
    rerender({ snapshot: storedLocalSkill('local::alpha'), open: true });
    await act(async () => {});

    expect(result.current.sheet.isEvolutionLocked).toBe(false);
  });

  it('reopens locked again after locking an unlocked skill', async () => {
    useSkillStore.setState({ localSkills: [buildLocalSkill('local::alpha', false)] });
    const { result, rerender } = renderSheet(storedLocalSkill('local::alpha'));
    await act(async () => {});

    await act(async () => {
      await result.current.sheet.handleToggleEvolutionLock();
    });
    expect(toggleEvolutionLockMock).toHaveBeenCalledWith('local::alpha', true);

    rerender({ snapshot: storedLocalSkill('local::alpha'), open: false });
    rerender({ snapshot: storedLocalSkill('local::alpha'), open: true });
    await act(async () => {});

    expect(result.current.sheet.isEvolutionLocked).toBe(true);
  });

  it('changes nothing when the server refuses the toggle', async () => {
    toggleEvolutionLockMock.mockRejectedValue(new Error('boom'));
    const { result } = renderSheet(storedLocalSkill('local::alpha'));
    await act(async () => {});

    await act(async () => {
      await result.current.sheet.handleToggleEvolutionLock();
    });

    expect(result.current.sheet.isEvolutionLocked).toBe(true);
    expect(storedLocalSkill('local::alpha').evolution_locked).toBe(true);
    expect(toastMock).toHaveBeenCalledWith({ title: 'detail.evolutionLockFailed', variant: 'destructive' });
  });
});
