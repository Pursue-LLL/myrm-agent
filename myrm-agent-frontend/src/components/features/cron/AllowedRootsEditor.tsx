'use client';

import { useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { FolderOpen, Plus, X } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { toast } from 'sonner';
import { updateCronJob } from '@/services/cron';
import type { EditorProps } from './CronDeliveryEditors';

const COMMON_PATHS = ['~/Documents', '~/Desktop', '/tmp', '~/Downloads'] as const;

export function AllowedRootsEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const serverRoots = job.allowed_roots ?? [];
  const [localRoots, setLocalRoots] = useState<string[]>(serverRoots);
  const [newPath, setNewPath] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLocalRoots(job.allowed_roots ?? []);
  }, [job.allowed_roots]);

  const sortedLocal = useMemo(() => [...localRoots].sort(), [localRoots]);
  const sortedServer = useMemo(() => [...serverRoots].sort(), [serverRoots]);

  const dirty = useMemo(
    () => sortedLocal.length !== sortedServer.length || sortedLocal.some((v, i) => v !== sortedServer[i]),
    [sortedLocal, sortedServer],
  );

  const addPath = (path: string) => {
    const trimmed = path.trim();
    if (!trimmed || localRoots.includes(trimmed)) return;
    setLocalRoots((prev) => [...prev, trimmed]);
    setNewPath('');
  };

  const removePath = (idx: number) => {
    setLocalRoots((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateCronJob(job.id, { allowed_roots: localRoots });
      onUpdated();
      toast.success(localRoots.length > 0 ? t('allowedRootsUpdated') : t('allowedRootsCleared'));
    } catch {
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <div className="flex items-center gap-1.5">
        <FolderOpen className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">{t('allowedRootsLabel')}</span>
      </div>
      <p className="text-[11px] text-muted-foreground">{t('allowedRootsDesc')}</p>

      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-[11px] text-muted-foreground">{t('commonPaths')}</span>
        {COMMON_PATHS.map((p) => (
          <button
            key={p}
            type="button"
            disabled={saving || localRoots.includes(p)}
            onClick={() => addPath(p)}
            className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
              localRoots.includes(p)
                ? 'bg-primary/10 text-primary border-primary/40'
                : 'bg-muted/50 text-muted-foreground border-border hover:bg-muted'
            }`}
          >
            {p}
          </button>
        ))}
      </div>

      {localRoots.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {localRoots.map((root, idx) => (
            <div
              key={`${root}-${idx}`}
              className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary/10 border border-primary/30 text-xs text-primary"
            >
              <code className="font-mono text-[11px]">{root}</code>
              <button
                type="button"
                onClick={() => removePath(idx)}
                disabled={saving}
                className="hover:text-destructive transition-colors"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2">
        <Input
          placeholder={t('pathPlaceholder')}
          value={newPath}
          onChange={(e) => setNewPath(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              addPath(newPath);
            }
          }}
          className="h-7 text-xs flex-1"
          disabled={saving}
        />
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs"
          onClick={() => addPath(newPath)}
          disabled={saving || !newPath.trim()}
        >
          <Plus className="h-3 w-3 mr-1" />
          {t('addPath')}
        </Button>
      </div>

      {localRoots.length === 0 && (
        <p className="text-[11px] text-muted-foreground/70 italic">{t('allowedRootsHint')}</p>
      )}

      {dirty && (
        <Button size="sm" className="h-7 text-xs" onClick={handleSave} disabled={saving}>
          {t('save')}
        </Button>
      )}
    </div>
  );
}
