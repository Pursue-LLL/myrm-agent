'use client';

import { useEffect } from 'react';
import { usePlanStore } from '@/store/chat/goals/usePlanStore';
import useChatStore from '@/store/useChatStore';

/** Hydrate goal todos from REST + live SSE `tasks_steps` updates.
 *  Also handles stale plan cleanup on chat switch and SSE reconnect. */
export function useGoalPlanSync(chatId: string | null | undefined): void {
  const fetchPlan = usePlanStore((s) => s.fetchPlan);
  const clearPlan = usePlanStore((s) => s.clearPlan);
  const clearActivePlan = usePlanStore((s) => s.clearActivePlan);
  const updateStepStatus = usePlanStore((s) => s.updateStepStatus);

  useEffect(() => {
    if (!chatId) {
      clearPlan();
      return;
    }

    clearPlan();
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

    const handleReconnect = () => {
      const isLoading = useChatStore.getState().loading;
      if (!isLoading) {
        clearActivePlan();
      }
      void fetchPlan(chatId);
    };

    window.addEventListener('tasks_steps', handlePlanUpdate);
    window.addEventListener('multiplex_reconnected', handleReconnect);
    return () => {
      window.removeEventListener('tasks_steps', handlePlanUpdate);
      window.removeEventListener('multiplex_reconnected', handleReconnect);
    };
  }, [chatId, fetchPlan, clearPlan, clearActivePlan, updateStepStatus]);
}
