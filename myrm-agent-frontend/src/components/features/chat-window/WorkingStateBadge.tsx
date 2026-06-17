'use client';

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconBrain } from '@/components/features/icons/PremiumIcons';
import { getWorkingState } from '@/services/memory';
import useChatStore from '@/store/useChatStore';

const WorkingStateBadge = memo(() => {
  const t = useTranslations('settings.workingState');
  const [content, setContent] = useState<string | null>(null);
  const loading = useChatStore((s) => s.loading);
  const prevLoadingRef = useRef(loading);

  const fetchState = useCallback(async () => {
    try {
      const res = await getWorkingState();
      setContent(res.content && !res.expired ? res.content : null);
    } catch {
      /* non-critical */
    }
  }, []);

  useEffect(() => {
    fetchState();
  }, [fetchState]);

  useEffect(() => {
    if (prevLoadingRef.current && !loading) {
      fetchState();
    }
    prevLoadingRef.current = loading;
  }, [loading, fetchState]);

  if (!content) return null;

  return (
    <div className="flex items-center gap-1.5 px-3 py-1 border-b border-primary/10 bg-primary/5 dark:bg-primary/10 text-xs text-primary/80 truncate">
      <IconBrain className="h-3 w-3 shrink-0" />
      <span className="truncate" title={content}>
        {t('title')}: {content}
      </span>
    </div>
  );
});

WorkingStateBadge.displayName = 'WorkingStateBadge';
export default WorkingStateBadge;
