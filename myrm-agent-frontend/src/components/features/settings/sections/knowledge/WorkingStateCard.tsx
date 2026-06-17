'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { motion } from 'framer-motion';
import {
  IconBrain,
  IconCheckCircle,
  IconLoader,
  IconTrash,
  IconRefresh,
} from '@/components/features/icons/PremiumIcons';
import { toast } from 'sonner';
import { cn } from '@/lib/utils/classnameUtils';
import {
  getWorkingState,
  updateWorkingState,
  clearWorkingState,
  type WorkingStateResponse,
} from '@/services/memory';

const WorkingStateCard = memo(() => {
  const t = useTranslations('settings.workingState');
  const [data, setData] = useState<WorkingStateResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [saving, setSaving] = useState(false);

  const fetchState = useCallback(async () => {
    try {
      const res = await getWorkingState();
      setData(res);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchState();
  }, [fetchState]);

  const handleClear = useCallback(async () => {
    try {
      await clearWorkingState();
      setData({ content: null, updated_at: null, ttl_days: 7, expired: false });
      toast.success(t('cleared'));
    } catch {
      toast.error(t('clearFailed'));
    }
  }, [t]);

  const handleSave = useCallback(async () => {
    if (!editContent.trim()) return;
    setSaving(true);
    try {
      const res = await updateWorkingState(editContent.trim());
      setData(res);
      setEditing(false);
      toast.success(t('saved'));
    } catch {
      toast.error(t('saveFailed'));
    } finally {
      setSaving(false);
    }
  }, [editContent, t]);

  const handleEdit = useCallback(() => {
    setEditContent(data?.content ?? '');
    setEditing(true);
  }, [data]);

  if (loading) {
    return (
      <div className="flex items-center justify-center p-6">
        <IconLoader className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const hasContent = data?.content && !data.expired;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        'rounded-xl border p-4 transition-colors',
        hasContent
          ? 'border-primary/20 bg-primary/5 dark:border-primary/30 dark:bg-primary/10'
          : 'border-border bg-card'
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <IconBrain className={cn('h-4 w-4', hasContent ? 'text-primary' : 'text-muted-foreground')} />
          <span className="text-sm font-medium">{t('title')}</span>
        </div>
        <div className="flex items-center gap-1">
          {hasContent && (
            <>
              <button
                onClick={handleEdit}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                title={t('edit')}
              >
                <IconRefresh className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={handleClear}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                title={t('clear')}
              >
                <IconTrash className="h-3.5 w-3.5" />
              </button>
            </>
          )}
        </div>
      </div>

      {editing ? (
        <div className="space-y-2">
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            className="w-full rounded-lg border border-border bg-background p-2 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-primary"
            rows={3}
            placeholder={t('placeholder')}
            autoFocus
          />
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setEditing(false)}
              className="rounded-md px-3 py-1 text-xs text-muted-foreground hover:bg-accent"
            >
              {t('cancel')}
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !editContent.trim()}
              className="rounded-md bg-primary px-3 py-1 text-xs text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {saving ? <IconLoader className="h-3 w-3 animate-spin" /> : t('save')}
            </button>
          </div>
        </div>
      ) : hasContent ? (
        <div className="space-y-1">
          <p className="text-sm text-foreground/80 leading-relaxed whitespace-pre-wrap">
            {data.content}
          </p>
          {data.updated_at && (
            <p className="text-xs text-muted-foreground">
              {t('updatedAt', { time: new Date(data.updated_at).toLocaleString() })}
            </p>
          )}
        </div>
      ) : (
        <div className="flex items-center justify-between text-muted-foreground">
          <div className="flex items-center gap-2">
            <IconCheckCircle className="h-4 w-4" />
            <span className="text-sm">{t('empty')}</span>
          </div>
          <button
            onClick={handleEdit}
            className="rounded-md px-2.5 py-1 text-xs text-primary hover:bg-primary/10 transition-colors"
          >
            {t('add')}
          </button>
        </div>
      )}
    </motion.div>
  );
});

WorkingStateCard.displayName = 'WorkingStateCard';
export default WorkingStateCard;
