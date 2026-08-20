/** @vitest-environment jsdom */

import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api';
import { useSkillDiscovery } from '../useSkillDiscovery';

const uninstallMock = vi.hoisted(() => vi.fn());

vi.mock('@/services/skill', () => ({
  searchDiscoverySkills: vi.fn().mockResolvedValue({
    total: 1,
    results: [
      {
        id: 'plugin-1',
        name: 'Plugin One',
        source: 'clawhub',
        tags: ['test'],
        stars: 10,
        downloads: 100,
        installed_skill_id: 'local::plugin-1',
        installed_version: '1.0.0',
      },
    ],
  }),
  previewDiscoverySkill: vi.fn(),
  installDiscoverySkill: vi.fn(),
  uninstallDiscoverySkill: uninstallMock,
}));

describe('useSkillDiscovery.uninstall', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('passes the force flag through to the API call', async () => {
    uninstallMock.mockResolvedValue({
      success: true,
      skill_id: 's1',
      skill_name: 'Skill One',
      version: '1.0.0',
    });
    const { result } = renderHook(() => useSkillDiscovery());

    await act(async () => {
      await result.current.uninstall('s1');
      await result.current.uninstall('s1', true);
    });

    expect(uninstallMock).toHaveBeenNthCalledWith(1, 's1', false);
    expect(uninstallMock).toHaveBeenNthCalledWith(2, 's1', true);
  });

  it('rethrows 409 dependency-guard errors so callers can offer force-uninstall', async () => {
    uninstallMock.mockRejectedValue(
      new ApiError('Skill is referenced by other skills', 409, [], undefined, 'DEPENDENTS_EXIST'),
    );
    const { result } = renderHook(() => useSkillDiscovery());

    await expect(result.current.uninstall('s1')).rejects.toThrow(ApiError);
  });

  it('swallows non-409 failures and reports false', async () => {
    uninstallMock.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useSkillDiscovery());

    let outcome = true;
    await act(async () => {
      outcome = await result.current.uninstall('s1');
    });
    expect(outcome).toBe(false);
  });

  it('updates results dynamically when skill_pool_updated event is received for uninstall', async () => {
    const { result } = renderHook(() => useSkillDiscovery());

    await act(async () => {
      await result.current.search('test');
    });

    expect(result.current.results.length).toBe(1);
    expect(result.current.results[0].installed_version).toBe('1.0.0');

    act(() => {
      window.dispatchEvent(
        new CustomEvent('skill_pool_updated', {
          detail: {
            action: 'uninstall',
            skill_id: 'local::plugin-1',
            uninstalled_skills: ['plugin-1', 'sub-skill-1'],
          },
        }),
      );
    });

    expect(result.current.results.length).toBe(1);
    expect(result.current.results[0].installed_version).toBeNull();
    expect(result.current.results[0].installed_skill_id).toBeNull();
  });
});
