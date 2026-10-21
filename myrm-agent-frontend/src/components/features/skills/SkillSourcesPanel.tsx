'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Globe, Plus, Trash2, Loader2, CheckCircle, XCircle } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { toast } from '@/hooks/shared/useToast';
import { getCustomSources, addCustomSource, removeCustomSource, type CustomSource } from '@/services/skill';

const SkillSourcesPanel = memo(() => {
  const t = useTranslations('settings.skills.discover.customSources');
  const [sources, setSources] = useState<CustomSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [addingUrl, setAddingUrl] = useState('');
  const [addingLabel, setAddingLabel] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [removingUrl, setRemovingUrl] = useState<string | null>(null);

  const fetchSources = useCallback(async () => {
    try {
      const res = await getCustomSources();
      setSources(res.sources);
    } catch {
      // Silent fail on initial load
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSources();
  }, [fetchSources]);

  const handleAdd = useCallback(async () => {
    if (!addingUrl.trim()) {
      return;
    }
    setIsAdding(true);
    try {
      const res = await addCustomSource(addingUrl.trim(), 'well-known', addingLabel.trim());
      toast({ title: t('addSuccess', { count: res.skill_count }), variant: 'default' });
      setAddingUrl('');
      setAddingLabel('');
      await fetchSources();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes('409') || msg.includes('already')) {
        toast({ title: t('alreadyExists'), variant: 'destructive' });
      } else if (msg.includes('422') || msg.includes('reach')) {
        toast({ title: t('unreachable'), variant: 'destructive' });
      } else {
        toast({ title: t('addFailed'), variant: 'destructive' });
      }
    } finally {
      setIsAdding(false);
    }
  }, [addingUrl, addingLabel, t, fetchSources]);

  const handleRemove = useCallback(
    async (url: string) => {
      setRemovingUrl(url);
      try {
        await removeCustomSource(url);
        toast({ title: t('removed'), variant: 'default' });
        await fetchSources();
      } catch {
        toast({ title: t('removeFailed'), variant: 'destructive' });
      } finally {
        setRemovingUrl(null);
      }
    },
    [t, fetchSources],
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Globe className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium">{t('title')}</span>
      </div>
      <p className="text-xs text-muted-foreground">{t('description')}</p>

      {/* Add source form */}
      <div className="flex items-center gap-2">
        <Input
          value={addingUrl}
          onChange={(e) => setAddingUrl(e.target.value)}
          placeholder={t('urlPlaceholder')}
          className="flex-1 h-8 text-sm"
          onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
        />
        <Input
          value={addingLabel}
          onChange={(e) => setAddingLabel(e.target.value)}
          placeholder={t('labelPlaceholder')}
          className="w-32 h-8 text-sm"
        />
        <Button variant="outline" size="sm" onClick={handleAdd} disabled={isAdding || !addingUrl.trim()}>
          {isAdding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
          <span className="ml-1">{isAdding ? t('adding') : t('addSource')}</span>
        </Button>
      </div>

      {/* Sources list */}
      {sources.length === 0 ? (
        <div className="py-4 text-center text-sm text-muted-foreground">
          <p>{t('empty')}</p>
          <p className="text-xs mt-1">{t('emptyDesc')}</p>
        </div>
      ) : (
        <div className="space-y-2">
          {sources.map((source) => (
            <div
              key={source.url}
              className={cn(
                'flex items-center justify-between rounded-md border px-3 py-2',
                'bg-card hover:bg-accent/50 transition-colors',
              )}
            >
              <div className="flex items-center gap-2 overflow-hidden">
                {source.healthy ? (
                  <CheckCircle className="h-3.5 w-3.5 text-green-500 shrink-0" />
                ) : (
                  <XCircle className="h-3.5 w-3.5 text-destructive shrink-0" />
                )}
                <div className="overflow-hidden">
                  <p className="text-sm font-medium truncate">{source.label || source.url}</p>
                  {source.label && <p className="text-xs text-muted-foreground truncate">{source.url}</p>}
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="shrink-0 text-muted-foreground hover:text-destructive"
                onClick={() => handleRemove(source.url)}
                disabled={removingUrl === source.url}
              >
                {removingUrl === source.url ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Trash2 className="h-3.5 w-3.5" />
                )}
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
});

SkillSourcesPanel.displayName = 'SkillSourcesPanel';
export default SkillSourcesPanel;
