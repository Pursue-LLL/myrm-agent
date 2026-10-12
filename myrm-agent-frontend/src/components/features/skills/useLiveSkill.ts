import { useSkillStore } from '@/store/skill';
import type { Skill } from '@/store/skill/types';

/**
 * The detail sheet opens on a snapshot of the skill. Availability changes server-side after the user saves keys,
 * so what the sheet displays follows the refreshed lists while its own effects keep keying off the snapshot
 * (a list refresh must not reload SKILL.md or discard unsaved key input).
 */
export function useLiveSkill(snapshot: Skill | null): Skill | null {
  const live = useSkillStore((state) =>
    snapshot ? [...state.marketSkills, ...state.localSkills].find((skill) => skill.id === snapshot.id) : undefined,
  );
  return live ?? snapshot;
}
