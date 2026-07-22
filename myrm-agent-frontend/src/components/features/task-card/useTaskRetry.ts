/**
 * [INPUT]
 * ./retryTask::retryTask (POS: Task retry transport and error parsing helper)
 *
 * [OUTPUT]
 * useTaskRetry: Shared retry state + handler for task cards.
 *
 * [POS]
 * Reusable UI hook for retrying failed tasks with consistent user-facing feedback.
 */

import React from 'react';
import type { TaskStatus } from '@/store/tasks/types';
import { retryTask, TaskRetryRequestError } from './retryTask';

interface UseTaskRetryResult {
  isRetrying: boolean;
  retryErrorMessage?: string;
  retry: () => Promise<void>;
}

export function useTaskRetry(taskId: string, taskStatus: TaskStatus | undefined): UseTaskRetryResult {
  const [isRetrying, setIsRetrying] = React.useState(false);
  const [retryErrorMessage, setRetryErrorMessage] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (taskStatus !== 'failed') {
      setRetryErrorMessage(null);
      setIsRetrying(false);
    }
  }, [taskStatus]);

  const retry = React.useCallback(async () => {
    setRetryErrorMessage(null);
    setIsRetrying(true);
    try {
      await retryTask(taskId);
    } catch (error) {
      if (error instanceof TaskRetryRequestError) {
        setRetryErrorMessage(error.message);
      } else {
        setRetryErrorMessage('Unable to retry task right now. Please try again.');
      }
      console.error('Failed to retry task:', error);
    } finally {
      setIsRetrying(false);
    }
  }, [taskId]);

  return {
    isRetrying,
    retryErrorMessage: retryErrorMessage ?? undefined,
    retry,
  };
}

