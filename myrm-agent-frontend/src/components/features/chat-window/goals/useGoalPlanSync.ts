'use client';

import { useEffect } from 'react';
import { usePlanStore } from '@/store/chat/goals/usePlanStore';

/** Hydrate goal todos from REST + live SSE `tasks_steps` updates. */
export function useGoalPlanSync(chatId: string | null | undefined): void {
  const fetchPlan = usePlanStore((s) => s.fetchPlan);
  const updateStepStatus = usePlanStore((s) => s.updateStepStatus);

  useEffect(() => {
    if (!chatId) return;

    void fetchPlan(chatId);

    const handlePlanUpdate = (event: Event) => {
      const detail = (event as CustomEvent).detail as {
        chat_id?: string;
        type?: string;
        step_key?: string;
        status?: string;
      } | null;
      if (!detail || detail.chat_id !== chatId || detail.type !== 'tasks_steps') {
        return;
      }

      const stepKey = detail.step_key;
      if (stepKey?.startsWith('todo_step_')) {
        const stepId = stepKey.replace('todo_step_', '');
        let status: 'pending' | 'in_progress' | 'completed' | 'skipped' = 'pending';
        if (detail.status === 'success') status = 'completed';
        else if (detail.status === 'running') status = 'in_progress';
        else if (detail.status === 'skipped') status = 'skipped';
        updateStepStatus(stepId, status);
        return;
      }

      if (stepKey === 'progress_root') {
        void fetchPlan(chatId);
      }
    };

    window.addEventListener('tasks_steps', handlePlanUpdate);
    return () => window.removeEventListener('tasks_steps', handlePlanUpdate);
  }, [chatId, fetchPlan, updateStepStatus]);
}
