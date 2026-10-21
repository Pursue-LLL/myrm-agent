// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { useTranslations } from 'next-intl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { installEnglishToastTranslator, jsonResponse, riskHeldRefusalBody, riskHeldTitle } from '@/test-utils/riskHeld';

const { sheetToast, riskToast } = vi.hoisted(() => ({
  sheetToast: vi.fn(),
  riskToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

vi.mock('@/hooks/shared/useToast', () => ({ toast: sheetToast }));
vi.mock('@/lib/utils/toast', () => ({ toast: riskToast }));

import type { Skill } from '@/store/skill/types';
import { useSkillDetailSheet } from '../useSkillDetailSheet';

const skill = {
  id: 'skill-1',
  name: 'Falcon',
  evolution_locked: false,
  requires: { bins: [], env: [], config: [] },
} as unknown as Skill;

const HELD_INSTRUCTION = 'rewrite it to use key sk-AAAAAABBBBBBCCCCCCDDDD-0';

function openOptimizer() {
  const hook = renderHook(() =>
    useSkillDetailSheet({
      skill,
      open: false,
      isEnabled: true,
      onOpenChange: vi.fn(),
      t: useTranslations('settings.skills'),
    }),
  );
  act(() => {
    hook.result.current.setShowOptimizeInput(true);
    hook.result.current.setOptimizeInstruction(HELD_INSTRUCTION);
  });
  return hook;
}

describe('optimizing a skill with an instruction the server holds', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installEnglishToastTranslator();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('explains the held instruction once, shows no failure toast and keeps the instruction for editing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(400, riskHeldRefusalBody)),
    );
    const hook = openOptimizer();

    await act(() => hook.result.current.handleOptimize());

    expect(riskToast.error).toHaveBeenCalledTimes(1);
    expect(riskToast.error.mock.calls[0]?.[0]).toBe(riskHeldTitle);
    expect(sheetToast).not.toHaveBeenCalled();
    expect(hook.result.current.showOptimizeInput).toBe(true);
    expect(hook.result.current.optimizeInstruction).toBe(HELD_INSTRUCTION);
    expect(hook.result.current.isOptimizing).toBe(false);
  });

  it('still reports any other failure with its own toast and the server message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(404, { detail: 'Skill not found' })),
    );
    const hook = openOptimizer();

    await act(() => hook.result.current.handleOptimize());

    expect(riskToast.error).not.toHaveBeenCalled();
    expect(sheetToast).toHaveBeenCalledWith({
      title: 'detail.optimizeFailed',
      description: 'Skill not found',
      variant: 'destructive',
    });
  });

  it.each([
    [
      'a structured detail',
      () => jsonResponse(422, { detail: [{ loc: ['body', 'instruction'], msg: 'field required' }] }),
    ],
    [
      'a proxy error page',
      () => new Response('<html>Bad Gateway</html>', { status: 502, headers: { 'Content-Type': 'text/html' } }),
    ],
  ])('reports %s as the localized failure, never as object text or a parser message', async (_name, respond) => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => respond()),
    );
    const hook = openOptimizer();

    await act(() => hook.result.current.handleOptimize());

    expect(riskToast.error).not.toHaveBeenCalled();
    expect(sheetToast).toHaveBeenCalledWith({
      title: 'detail.optimizeFailed',
      description: 'detail.optimizeFailed',
      variant: 'destructive',
    });
  });
});
