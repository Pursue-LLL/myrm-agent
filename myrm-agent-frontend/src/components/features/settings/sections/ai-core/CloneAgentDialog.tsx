'use client';

import { useState, useCallback, useEffect } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { Input } from '@/components/primitives/input';
import { toast } from '@/hooks/useToast';
import { cloneAgent, Agent } from '@/services/agent';

interface CloneAgentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agentId: string | null;
  agentName: string | null;
  onCloned: (agent: Agent) => void;
}

export default function CloneAgentDialog({ open, onOpenChange, agentId, agentName, onCloned }: CloneAgentDialogProps) {
  const t = useTranslations();
  const locale = useLocale();

  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open && agentName) {
      setName(`${agentName} (${locale === 'zh' ? '副本' : 'Copy'})`);
    }
  }, [open, agentName, locale]);

  const resetAndClose = useCallback(() => {
    setName('');
    setLoading(false);
    onOpenChange(false);
  }, [onOpenChange]);

  const handleClone = useCallback(async () => {
    if (!agentId || !name.trim()) return;
    setLoading(true);
    try {
      const cloned = await cloneAgent(agentId, name.trim());
      toast({ title: t('agent.cloneSuccess') });
      onCloned(cloned);
      resetAndClose();
    } catch (err: unknown) {
      toast({
        title: t('agent.operationFailed'),
        description: err instanceof Error ? err.message : undefined,
        variant: 'destructive',
      });
      setLoading(false);
    }
  }, [agentId, name, t, onCloned, resetAndClose]);

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="rounded-2xl">
        <AlertDialogHeader>
          <AlertDialogTitle>{t('agent.cloneDialogTitle')}</AlertDialogTitle>
          <AlertDialogDescription>{t('agent.cloneDialogDesc')}</AlertDialogDescription>
        </AlertDialogHeader>
        <div className="px-1 py-2">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('agent.cloneNamePlaceholder')}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter' && name.trim() && !loading) {
                handleClone();
              }
            }}
          />
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel className="rounded-xl">{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction onClick={handleClone} disabled={!name.trim() || loading} className="rounded-xl">
            {loading ? t('agent.loading') : t('agent.clone')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
