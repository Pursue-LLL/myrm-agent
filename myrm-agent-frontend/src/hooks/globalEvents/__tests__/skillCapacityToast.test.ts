import { describe, expect, it, vi } from 'vitest';

import { showSkillCapacityToast, type SkillCapacityToastDeps } from '@/hooks/globalEvents/skillCapacityToast';

function buildDeps() {
  const warning = vi.fn();
  const push = vi.fn();
  const deps: SkillCapacityToastDeps = {
    t: (key, values) => (values ? `${key}:${values.max}` : key),
    router: { push },
    toast: { warning },
  };
  return { deps, warning, push };
}

describe('showSkillCapacityToast', () => {
  it('shows localized copy with the library limit as a single replaceable toast', () => {
    const { deps, warning } = buildDeps();

    showSkillCapacityToast({ agent_id: 'agent-1', current_count: 50, max_count: 50 }, deps);

    expect(warning).toHaveBeenCalledOnce();
    expect(warning).toHaveBeenCalledWith(
      'skillCapacityReached:50',
      expect.objectContaining({
        id: 'skill-capacity-reached',
        description: 'skillCapacityReachedHint',
        duration: 12_000,
        dismissible: true,
      }),
    );
  });

  it('opens the skills settings from the toast action', () => {
    const { deps, warning, push } = buildDeps();

    showSkillCapacityToast({ max_count: 50 }, deps);
    const options = warning.mock.calls[0][1] as { action: { label: string; onClick: () => void } };
    expect(options.action.label).toBe('manageSkills');
    options.action.onClick();

    expect(push).toHaveBeenCalledOnce();
    expect(push).toHaveBeenCalledWith('/settings/skills');
  });

  it.each([{}, { max_count: 'many' }, { max_count: null }])('shows nothing without a usable limit: %j', (data) => {
    const { deps, warning } = buildDeps();

    showSkillCapacityToast(data, deps);

    expect(warning).not.toHaveBeenCalled();
  });
});
