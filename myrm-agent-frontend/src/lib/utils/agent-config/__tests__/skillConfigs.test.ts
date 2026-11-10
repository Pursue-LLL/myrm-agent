import { describe, expect, it } from 'vitest';
import { areSkillConfigsEqual } from '../skillConfigs';

describe('areSkillConfigsEqual', () => {
  it('treats a missing map like an empty one', () => {
    expect(areSkillConfigsEqual(undefined, {})).toBe(true);
    expect(areSkillConfigsEqual(undefined, undefined)).toBe(true);
  });

  it('treats a null instance_name like a missing one and a missing is_core like false', () => {
    expect(
      areSkillConfigsEqual({ 'skill-a': { is_core: true, instance_name: null } }, { 'skill-a': { is_core: true } }),
    ).toBe(true);
    expect(areSkillConfigsEqual({ 'skill-a': {} }, { 'skill-a': { is_core: false, instance_name: null } })).toBe(true);
  });

  it('detects an instance_name change', () => {
    expect(
      areSkillConfigsEqual(
        { 'skill-a': { is_core: true, instance_name: null } },
        { 'skill-a': { is_core: true, instance_name: 'work' } },
      ),
    ).toBe(false);
  });

  it('detects an is_core change', () => {
    expect(
      areSkillConfigsEqual(
        { 'skill-a': { is_core: true, instance_name: null } },
        { 'skill-a': { is_core: false, instance_name: null } },
      ),
    ).toBe(false);
  });

  it('detects a skill that is present on one side only, whatever the sizes', () => {
    expect(areSkillConfigsEqual({ a: {} }, {})).toBe(false);
    expect(areSkillConfigsEqual({ a: {} }, { b: {} })).toBe(false);
  });

  it('ignores key order', () => {
    expect(
      areSkillConfigsEqual(
        { a: { is_core: true, instance_name: null }, b: { is_core: false, instance_name: 'x' } },
        { b: { is_core: false, instance_name: 'x' }, a: { is_core: true, instance_name: null } },
      ),
    ).toBe(true);
  });
});
