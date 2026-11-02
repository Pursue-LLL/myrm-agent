'use client';

/**
 * [INPUT]
 * - @/services/background-tasks::{cancelBackgroundTask,sendShellBackgroundStdin,steerBackgroundTask}
 *   (POS: REST client for the background-tasks endpoints)
 * - @/services/mediaTasks::cancelMediaTask (POS: REST client for `/api/v1/tasks` media jobs)
 * - @/services/riskHeldToast::isRiskHeldError
 *   (POS: tells whether an error is a risk-rule refusal whose notice is already shown)
 * - @/lib/utils/toast::toast (POS: toast wrapper over Sonner)
 * - ./BackgroundTaskRow::BackgroundTaskRowActions (POS: contract of what a row can do on its task)
 *
 * [OUTPUT]
 * - useBackgroundTaskActions: `rowActions` for the Shell and Agent rows of BackgroundTasksPanel (cancel, stop what a
 *   finished task left running, steer, shell stdin) and `handleCancelMediaTask` for media rows
 *
 * [POS]
 * Row action handlers of BackgroundTasksPanel. Each answers with a toast; cancel, stop-leftover and stdin refresh the
 * task list, a media cancel refreshes the media list, and a steer only closes its input.
 */

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/lib/utils/toast';
import { cancelBackgroundTask, sendShellBackgroundStdin, steerBackgroundTask } from '@/services/background-tasks';
import { cancelMediaTask } from '@/services/mediaTasks';
import { isRiskHeldError } from '@/services/riskHeldToast';
import type { BackgroundTaskRowActions } from './BackgroundTaskRow';

interface TaskListRefreshers {
  fetchTasks: () => Promise<void>;
  refetchMediaTasks: () => Promise<void>;
}

/**
 * What the panel's rows do on a task: cancel it, stop what a finished one left running, steer it, and feed or close a
 * shell's stdin. Each is answered with a toast. The steer and stdin inputs are never open together, and only on one
 * task.
 */
export function useBackgroundTaskActions({ fetchTasks, refetchMediaTasks }: TaskListRefreshers) {
  const t = useTranslations('backgroundTasks');
  const [steerTaskId, setSteerTaskId] = useState<string | null>(null);
  const [steerInput, setSteerInput] = useState('');
  const [shellInputTaskId, setShellInputTaskId] = useState<string | null>(null);
  const [shellInput, setShellInput] = useState('');

  const handleCancel = async (taskId: string) => {
    try {
      await cancelBackgroundTask(taskId);
      toast.success(t('cancelSuccess'));
      void fetchTasks();
    } catch {
      toast.error(t('cancelFailed'));
    }
  };

  // The task itself is already finished: what is stopped is the program it left running. The server answers success
  // once the signal went out, so survivors are read from its scan: they stay on the row and the toast says so.
  const handleStopLeftover = async (taskId: string) => {
    try {
      const { leftover_processes: survivors = 0 } = await cancelBackgroundTask(taskId);
      if (survivors > 0) {
        toast.error(t('leftoverStopFailed'));
      } else {
        toast.success(t('leftoverStopSuccess'));
      }
      void fetchTasks();
    } catch {
      toast.error(t('leftoverStopFailed'));
    }
  };

  const handleCancelMediaTask = async (taskId: string) => {
    try {
      await cancelMediaTask(taskId);
      toast.success(t('cancelSuccess'));
      void refetchMediaTasks();
    } catch {
      toast.error(t('cancelFailed'));
    }
  };

  const handleSteer = async (taskId: string) => {
    if (!steerInput.trim()) {
      return;
    }
    try {
      await steerBackgroundTask(taskId, steerInput.trim());
      toast.success(t('steerSuccess'));
      setSteerTaskId(null);
      setSteerInput('');
    } catch (error) {
      // `apiRequest` has already shown the notice for a held instruction; a second toast would repeat it.
      if (!isRiskHeldError(error)) {
        toast.error(t('steerFailed'));
      }
    }
  };

  const handleToggleSteer = (taskId: string) => {
    setSteerTaskId((current) => (current === taskId ? null : taskId));
    setSteerInput('');
    setShellInputTaskId(null);
    setShellInput('');
  };

  const handleToggleShellInput = (taskId: string) => {
    setShellInputTaskId((current) => (current === taskId ? null : taskId));
    setShellInput('');
    setSteerTaskId(null);
    setSteerInput('');
  };

  const handleShellInputSend = async (taskId: string, value?: string) => {
    const nextValue = value ?? shellInput;
    if (value === undefined && !nextValue.trim()) {
      return;
    }
    try {
      await sendShellBackgroundStdin(taskId, nextValue, { submit: true });
      toast.success(t('shellInputSuccess'));
      setShellInputTaskId(null);
      setShellInput('');
      void fetchTasks();
    } catch {
      toast.error(t('shellInputFailed'));
    }
  };

  const handleShellInputClose = async (taskId: string) => {
    try {
      await sendShellBackgroundStdin(taskId, '', { close: true });
      toast.success(t('shellInputCloseSuccess'));
      setShellInputTaskId(null);
      setShellInput('');
      void fetchTasks();
    } catch {
      toast.error(t('shellInputCloseFailed'));
    }
  };

  const rowActions: BackgroundTaskRowActions = {
    steerTaskId,
    shellInputTaskId,
    steerInput,
    shellInput,
    onSteerInputChange: setSteerInput,
    onShellInputChange: setShellInput,
    onToggleSteer: handleToggleSteer,
    onToggleShellInput: handleToggleShellInput,
    onSteer: handleSteer,
    onShellInputSend: handleShellInputSend,
    onShellInputClose: handleShellInputClose,
    onPromptOptionSelect: (taskId, option) => handleShellInputSend(taskId, option.value),
    onCancel: handleCancel,
    onStopLeftover: handleStopLeftover,
  };

  return { rowActions, handleCancelMediaTask };
}
