'use client';

import { memo, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { BookmarkPlus, Loader2 } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Switch } from '@/components/primitives/switch';
import type { Message } from '@/store/chat/types/messages';
import { saveWorkflowTemplateFromRun } from '@/services/workflowTemplates';
import { useToast } from '@/hooks/shared/useToast';

interface WorkflowTemplateSaveCardProps {
  message: Message;
  chatId: string;
}

function isDynamicWorkflowMessage(message: Message): boolean {
  return Boolean(
    message.progressSteps?.some(
      (step) => step.step_key === 'workflow_init' || step.step_key === 'workflow_execution',
    ),
  );
}

const WorkflowTemplateSaveCard = memo(({ message, chatId }: WorkflowTemplateSaveCardProps) => {
  const t = useTranslations('chat.message.workflowTemplateSave');
  const { toast } = useToast();
  const [displayName, setDisplayName] = useState('');
  const [templateId, setTemplateId] = useState('');
  const [trustLatch, setTrustLatch] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const visible = useMemo(() => {
    if (message.role !== 'assistant') {return false;}
    if (saved) {return false;}
    if (message.completionStatus === 'error' || message.completionStatus === 'cancelled') {return false;}
    return isDynamicWorkflowMessage(message);
  }, [message, saved]);

  if (!visible) {
    return null;
  }

  const handleSave = async () => {
    const normalizedName = displayName.trim();
    const normalizedId = templateId.trim();
    if (!normalizedName || !normalizedId) {
      toast({ title: t('fieldsRequired'), variant: 'destructive' });
      return;
    }
    setSaving(true);
    try {
      await saveWorkflowTemplateFromRun({
        chat_id: chatId,
        message_id: message.messageId,
        template_id: normalizedId,
        display_name: normalizedName,
        trust_latch: trustLatch,
      });
      setSaved(true);
      toast({ title: t('success') });
    } catch (err) {
      toast({
        title: t('failed'),
        description: err instanceof Error ? err.message : undefined,
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mt-3 rounded-xl border border-primary/20 bg-primary/[0.03] px-4 py-3 space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
        <BookmarkPlus className="h-4 w-4 text-primary" />
        {t('title')}
      </div>
      <p className="text-xs text-muted-foreground">{t('description')}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Input
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          placeholder={t('displayNamePlaceholder')}
        />
        <Input
          value={templateId}
          onChange={(event) => setTemplateId(event.target.value)}
          placeholder={t('templateIdPlaceholder')}
        />
      </div>
      <div className="flex items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Switch checked={trustLatch} onCheckedChange={setTrustLatch} />
          {t('trustLatch')}
        </label>
        <Button size="sm" onClick={() => void handleSave()} disabled={saving} className="gap-1.5">
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <BookmarkPlus className="h-3.5 w-3.5" />}
          {t('save')}
        </Button>
      </div>
    </div>
  );
});

WorkflowTemplateSaveCard.displayName = 'WorkflowTemplateSaveCard';

export default WorkflowTemplateSaveCard;
