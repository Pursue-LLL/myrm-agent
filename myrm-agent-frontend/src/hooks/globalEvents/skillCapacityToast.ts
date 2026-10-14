/**
 * [INPUT] SETTINGS_SKILLS_PATH: 技能设置页路由（lib/skills/integrationOAuthDisplay）
 * [OUTPUT] showSkillCapacityToast: 技能库已满的本地化警告 toast，操作直达技能管理；
 *          SkillCapacityToastDeps: 它所需的翻译、路由与 toast 能力
 * [POS] 技能库已满提示。服务端以 `skill_capacity_reached` 事件下发（每次填满只发一次），这里只展示本地化文案与上限数量，
 *       不展示服务端措辞与 agent 标识；同一时刻只保留一条提示。
 */

import { SETTINGS_SKILLS_PATH } from '@/lib/skills/integrationOAuthDisplay';

const SKILL_CAPACITY_TOAST_ID = 'skill-capacity-reached';
const SKILL_CAPACITY_TOAST_DURATION_MS = 12_000;

export interface SkillCapacityToastDeps {
  t: (key: string, values?: Record<string, number>) => string;
  router: { push: (href: string) => void };
  toast: {
    warning: (
      message: string,
      options: {
        id: string;
        description: string;
        duration: number;
        dismissible: boolean;
        action: { label: string; onClick: () => void };
      },
    ) => void;
  };
}

export function showSkillCapacityToast(data: Record<string, unknown>, deps: SkillCapacityToastDeps): void {
  const max = data.max_count;
  if (typeof max !== 'number' || !Number.isFinite(max)) {
    return;
  }
  const { t, router, toast } = deps;
  toast.warning(t('skillCapacityReached', { max }), {
    id: SKILL_CAPACITY_TOAST_ID,
    description: t('skillCapacityReachedHint'),
    duration: SKILL_CAPACITY_TOAST_DURATION_MS,
    dismissible: true,
    action: { label: t('manageSkills'), onClick: () => router.push(SETTINGS_SKILLS_PATH) },
  });
}
