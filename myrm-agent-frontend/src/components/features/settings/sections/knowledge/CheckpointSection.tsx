'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import CheckpointList from '../../../checkpoint/CheckpointList';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import useChatStore from '@/store/useChatStore';
import { toast } from 'sonner';

/**
 * CheckpointSection - Checkpoint management settings panel
 *
 * Features:
 * - Display all saved checkpoints
 * - Re-initiate a checkpoint, pre-filling the chat input with the original
 *   task description so the user can restart the interrupted task
 * - Delete old checkpoints
 * - Cleanup expired checkpoints
 */
const CheckpointSection: React.FC = () => {
  const t = useTranslations('settings.checkpoint');
  const router = useRouter();
  const sessionId = useChatStore((state) => state.chatId);

  const handleReinitiate = (description: string, cpSessionId: string) => {
    useChatStore.getState().setInputMessage(description);
    if (cpSessionId) {
      useChatStore.getState().setChatId(cpSessionId);
    }
    toast.info(t('reinitiateInfo'), {
      description: description.slice(0, 80),
    });
    // Jump back to the chat page where the message is pre-filled
    router.push('/');
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
          <CheckpointList
            sessionId={sessionId}
            onReinitiate={handleReinitiate}
          />
        </CardContent>
      </Card>
    </div>
  );
};

export default CheckpointSection;
