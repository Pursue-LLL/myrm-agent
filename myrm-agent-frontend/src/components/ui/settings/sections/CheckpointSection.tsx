'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import CheckpointList from '../../checkpoint/CheckpointList';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import useChatStore from '@/store/useChatStore';
import { toast } from 'sonner';

/**
 * CheckpointSection - Checkpoint management settings panel
 *
 * Features:
 * - Display all saved checkpoints
 * - Resume interrupted agent tasks
 * - Delete old checkpoints
 * - Cleanup expired checkpoints
 */
const CheckpointSection: React.FC = () => {
  const t = useTranslations('settings.checkpoint');
  const sessionId = useChatStore((state) => state.chatId);

  const handleResumeSuccess = (taskId: string, newSessionId: string) => {
    toast.success(t('resumeSuccess'), {
      description: t('resumeSuccessDesc', { taskId: taskId.slice(0, 8) }),
    });
    // Navigate to the resumed session if needed
    if (newSessionId) {
      useChatStore.getState().setChatId(newSessionId);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">{t('title')}</h2>
        <p className="text-muted-foreground mt-1">{t('description')}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t('savedCheckpoints')}</CardTitle>
          <CardDescription>{t('savedCheckpointsDesc')}</CardDescription>
        </CardHeader>
        <CardContent>
          <CheckpointList sessionId={sessionId} onResumeSuccess={handleResumeSuccess} />
        </CardContent>
      </Card>
    </div>
  );
};

export default CheckpointSection;
