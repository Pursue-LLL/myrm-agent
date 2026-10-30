// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { MockLocale } from '@/test-utils/realIntl';
import type { Skill } from '@/store/skill/types';

const { hook, intl } = vi.hoisted(() => ({
  hook: { state: {} as Record<string, unknown> },
  intl: { locale: 'en' as MockLocale },
}));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));
vi.mock('../useSkillDetailSheet', () => ({ useSkillDetailSheet: () => hook.state }));
vi.mock('../useLiveSkill', () => ({ useLiveSkill: (skill: Skill) => skill }));
vi.mock('../SkillDetailSheetContent', () => ({ SkillDetailSheetContent: () => null }));
vi.mock('../SkillExportDialog', () => ({ default: () => null }));

import SkillDetailSheet from '../SkillDetailSheet';

const localSkill = {
  id: 'local::0123abcd',
  name: 'Falcon',
  type: 'local',
  version: '1.0.0',
  category: 'other',
  always: false,
  requires: { bins: [], env: [], config: [] },
} as unknown as Skill;

const prebuiltSkill = { ...localSkill, id: 'prebuilt-falcon', type: 'prebuilt' } as unknown as Skill;

function sheetState(overrides: Record<string, unknown> = {}) {
  return {
    isEvolutionLocked: false,
    isTogglingLock: false,
    handleToggleEvolutionLock: vi.fn(),
    isOptimizing: false,
    showOptimizeInput: false,
    optimizeInstruction: '',
    isDeleting: false,
    isToggling: false,
    isTrusting: false,
    showDeleteConfirm: false,
    showTrustConfirm: false,
    showExportDialog: false,
    setShowOptimizeInput: vi.fn(),
    setOptimizeInstruction: vi.fn(),
    setShowExportDialog: vi.fn(),
    setShowDeleteConfirm: vi.fn(),
    setShowTrustConfirm: vi.fn(),
    handleOptimize: vi.fn(),
    handleToggle: vi.fn(),
    handleDelete: vi.fn(),
    handleTrust: vi.fn(),
    ...overrides,
  };
}

function renderSheet(skill: Skill, overrides: Record<string, unknown> = {}) {
  hook.state = sheetState(overrides);
  render(<SkillDetailSheet skill={skill} open isEnabled onOpenChange={vi.fn()} />);
  return hook.state as ReturnType<typeof sheetState>;
}

describe('the Optimize action of a locked skill', () => {
  beforeEach(() => {
    intl.locale = 'en';
  });

  it('says why it is off and offers the unlock that turns it on', () => {
    const state = renderSheet(localSkill, { isEvolutionLocked: true });

    const notice = screen.getByRole('status');
    expect(notice.textContent).toContain('Evolution Protection');
    expect(notice.textContent).toContain('automatically');
    expect(screen.getByRole('button', { name: 'Optimize' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Unlock' }));
    expect(state.handleToggleEvolutionLock).toHaveBeenCalledTimes(1);
  });

  it('says it in the interface language, with the consequence of unlocking', () => {
    intl.locale = 'zh';
    renderSheet(localSkill, { isEvolutionLocked: true });

    expect(screen.getByRole('status').textContent).toContain('自动进化');
    expect(screen.getByRole('button', { name: '解锁' })).toBeEnabled();
  });

  it('keeps the unlock from firing twice while the lock is being changed', () => {
    renderSheet(localSkill, { isEvolutionLocked: true, isTogglingLock: true });

    expect(screen.getByRole('button', { name: 'Unlock' })).toBeDisabled();
  });

  it('shows no notice once the skill is unlocked, and Optimize works', () => {
    renderSheet(localSkill, { isEvolutionLocked: false });

    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.getByRole('button', { name: 'Optimize' })).toBeEnabled();
  });

  it('offers neither Optimize nor the notice for a skill that is not local', () => {
    renderSheet(prebuiltSkill, { isEvolutionLocked: true });

    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Optimize' })).toBeNull();
  });
});
