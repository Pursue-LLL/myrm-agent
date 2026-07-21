/**
 * [POS] 幂等被动里程碑触发器。先检查 store 再发请求，失败静默不阻塞主流程。
 */

import { useProgressionStore } from '@/store/useProgressionStore';

const TOAST_ZH: Record<string, string> = {
  first_chat: '首次对话已完成',
  first_tool_use: '首次工具调用已完成',
  first_approval: '首次审批闭环已完成',
  first_remote_takeover: '首次远程接管已完成',
  first_multistep_delivery: '首次多步骤交付已完成',
};

const TOAST_EN: Record<string, string> = {
  first_chat: 'First chat completed',
  first_tool_use: 'First tool use completed',
  first_approval: 'First approval completed',
  first_remote_takeover: 'First remote takeover completed',
  first_multistep_delivery: 'First multi-step delivery completed',
};

function getLevelUpMessage(milestoneId: string, newLevel: number): string {
  const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
  const isZh = lang?.startsWith('zh');
  const desc = isZh ? (TOAST_ZH[milestoneId] ?? '') : (TOAST_EN[milestoneId] ?? '');
  return isZh ? `升级到 L${newLevel}！${desc}` : `Leveled up to L${newLevel}! ${desc}`;
}

export function tryMarkMilestone(milestoneId: string): void {
  const { milestones, currentLevel, markMilestone } = useProgressionStore.getState();

  if (milestones.some((m) => m.id === milestoneId && m.completed_at !== null)) return;

  const prevLevel = currentLevel;

  void markMilestone(milestoneId).then(() => {
    const newLevel = useProgressionStore.getState().currentLevel;
    if (newLevel > prevLevel) {
      void import('@/lib/utils/toast').then(({ toast }) => {
        toast.success(getLevelUpMessage(milestoneId, newLevel));
      });
    }
  });
}
