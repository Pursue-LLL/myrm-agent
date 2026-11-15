/**
 * [INPUT]
 * next-intl::useTranslations (POS: Locale string resolver for task-card copy)
 * next/link::Link (POS: Client-side navigation)
 * ./TaskCardNotice (POS: Neutral task state card shell)
 *
 * [OUTPUT]
 * TaskCardExpired: State of a task card whose task record no longer exists.
 *
 * [POS]
 * Task records are pruned after 30 days, but the files they produced live on in the media library.
 * The card says so and points there, instead of showing a spinner that never ends.
 */

import React from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import TaskCardNotice from './TaskCardNotice';

interface TaskCardExpiredProps {
  className?: string;
}

export const TaskCardExpired: React.FC<TaskCardExpiredProps> = ({ className }) => {
  const t = useTranslations('taskCard');

  return (
    <TaskCardNotice className={className}>
      {t('expired')}{' '}
      <Link href="/library" className="font-medium text-foreground underline underline-offset-2 hover:text-primary">
        {t('openLibrary')}
      </Link>
    </TaskCardNotice>
  );
};

export default TaskCardExpired;
