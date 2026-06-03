'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/primitives/dialog';
import { useMemoryStore, type MemoryType } from '@/store/memory';
import type { CreateMemoryRequest } from '@/services/memory';
import MemoryTypeIcon from './MemoryTypeIcon';
import { toast } from '@/hooks/useToast';

interface MemoryCreateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const MEMORY_TYPES: MemoryType[] = ['profile', 'semantic', 'episodic', 'procedural'];

interface FormState {
  memory_type: MemoryType;
  content: string;
  importance: number;
  key: string;
  value: string;
  trigger: string;
  action: string;
}

const INITIAL_FORM: FormState = {
  memory_type: 'semantic',
  content: '',
  importance: 0.5,
  key: '',
  value: '',
  trigger: '',
  action: '',
};

const MemoryCreateDialog = memo<MemoryCreateDialogProps>(({ open, onOpenChange }) => {
  const t = useTranslations('memory');
  const tCommon = useTranslations('common');
  const { createMemory } = useMemoryStore();

  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (open) setForm(INITIAL_FORM);
  }, [open]);

  const updateField = useCallback(<K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  }, []);

  const isValid = (() => {
    switch (form.memory_type) {
      case 'profile':
        return form.key.trim().length > 0 && form.value.trim().length > 0;
      case 'procedural':
        return form.trigger.trim().length > 0 && form.action.trim().length > 0;
      default:
        return form.content.trim().length > 0;
    }
  })();

  const handleSubmit = useCallback(async () => {
    if (!isValid) return;
    setIsSubmitting(true);
    try {
      const body: CreateMemoryRequest = {
        memory_type: form.memory_type,
        content: '',
        importance: form.importance,
      };

      if (form.memory_type === 'profile') {
        body.content = `${form.key}: ${form.value}`;
        body.key = form.key.trim();
        body.value = form.value.trim();
      } else if (form.memory_type === 'procedural') {
        body.content = `${form.trigger} → ${form.action}`;
        body.trigger = form.trigger.trim();
        body.action = form.action.trim();
      } else {
        body.content = form.content.trim();
      }

      await createMemory(body);
      toast({ title: t('createDialog.success'), description: t('createDialog.successDesc') });
      onOpenChange(false);
    } catch (error) {
      toast({
        title: t('createDialog.failed'),
        description: error instanceof Error ? error.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setIsSubmitting(false);
    }
  }, [isValid, form, createMemory, t, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{t('createDialog.title')}</DialogTitle>
          <DialogDescription>{t('createDialog.description')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-2">
          {/* Type selector */}
          <div className="grid grid-cols-4 gap-2">
            {MEMORY_TYPES.map((type) => (
              <button
                key={type}
                onClick={() => updateField('memory_type', type)}
                className={cn(
                  'flex flex-col items-center gap-1.5 p-3 rounded-xl border transition-all duration-200',
                  form.memory_type === type
                    ? 'border-primary bg-primary/5 ring-2 ring-primary/20'
                    : 'border-border/50 hover:border-border hover:bg-accent/30',
                )}
              >
                <MemoryTypeIcon type={type} size={20} showBackground />
                <span className="text-xs font-medium">{t(`types.${type}`)}</span>
              </button>
            ))}
          </div>

          {/* Type description */}
          <p className="text-xs text-muted-foreground bg-accent/30 rounded-lg px-3 py-2">
            {t(`typeTooltips.${form.memory_type}.description`)}
          </p>

          {/* Dynamic form fields */}
          {form.memory_type === 'profile' && (
            <div className="space-y-3">
              <input
                type="text"
                value={form.key}
                onChange={(e) => updateField('key', e.target.value)}
                placeholder={t('createDialog.keyPlaceholder')}
                maxLength={100}
                className={cn(
                  'w-full px-3 py-2.5 rounded-lg text-sm',
                  'bg-accent/30 border border-border/50',
                  'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
                  'transition-all',
                )}
              />
              <input
                type="text"
                value={form.value}
                onChange={(e) => updateField('value', e.target.value)}
                placeholder={t('createDialog.valuePlaceholder')}
                maxLength={500}
                className={cn(
                  'w-full px-3 py-2.5 rounded-lg text-sm',
                  'bg-accent/30 border border-border/50',
                  'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
                  'transition-all',
                )}
              />
            </div>
          )}

          {form.memory_type === 'procedural' && (
            <div className="space-y-3">
              <input
                type="text"
                value={form.trigger}
                onChange={(e) => updateField('trigger', e.target.value)}
                placeholder={t('createDialog.triggerPlaceholder')}
                maxLength={500}
                className={cn(
                  'w-full px-3 py-2.5 rounded-lg text-sm',
                  'bg-accent/30 border border-border/50',
                  'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
                  'transition-all',
                )}
              />
              <input
                type="text"
                value={form.action}
                onChange={(e) => updateField('action', e.target.value)}
                placeholder={t('createDialog.actionPlaceholder')}
                maxLength={500}
                className={cn(
                  'w-full px-3 py-2.5 rounded-lg text-sm',
                  'bg-accent/30 border border-border/50',
                  'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
                  'transition-all',
                )}
              />
            </div>
          )}

          {(form.memory_type === 'semantic' || form.memory_type === 'episodic') && (
            <textarea
              value={form.content}
              onChange={(e) => updateField('content', e.target.value)}
              placeholder={t('createDialog.contentPlaceholder')}
              maxLength={2000}
              rows={4}
              className={cn(
                'w-full px-3 py-2.5 rounded-lg text-sm resize-none',
                'bg-accent/30 border border-border/50',
                'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
                'transition-all',
              )}
            />
          )}

          {/* Importance slider */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-foreground">{t('importance')}</label>
              <span className="text-xs text-muted-foreground tabular-nums">{form.importance.toFixed(1)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.1}
              value={form.importance}
              onChange={(e) => updateField('importance', parseFloat(e.target.value))}
              className="w-full accent-primary"
            />
          </div>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <button
            onClick={() => onOpenChange(false)}
            disabled={isSubmitting}
            className={cn(
              'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
              'border border-border/50 hover:bg-accent',
            )}
          >
            {tCommon('cancel')}
          </button>
          <button
            onClick={handleSubmit}
            disabled={isSubmitting || !isValid}
            className={cn(
              'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
              'bg-primary text-primary-foreground hover:bg-primary/90',
              'disabled:opacity-50 disabled:cursor-not-allowed',
            )}
          >
            {isSubmitting ? <Loader2 size={14} className="animate-spin" /> : t('createDialog.submit')}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
});

MemoryCreateDialog.displayName = 'MemoryCreateDialog';

export default MemoryCreateDialog;
