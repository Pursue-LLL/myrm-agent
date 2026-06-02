'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconFolder } from '@/components/ui/icons/PremiumIcons';
import { IconLock, IconPlus, IconX } from '@/components/ui/icons/PremiumIcons';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const DEFAULT_FORBIDDEN_PATHS = [
  '~/.ssh',
  '~/.gnupg',
  '~/.gpg',
  '~/.aws',
  '~/.config/gcloud',
  '~/.azure',
  '~/.bash_history',
  '~/.zsh_history',
  '/etc/shadow',
  '/etc/passwd',
  '/proc',
  '/sys',
];

interface PathPolicyEditorProps {
  allowedRoots: string[];
  onAdd: (path: string) => void;
  onRemove: (idx: number) => void;
}

export function PathPolicyEditor({ allowedRoots, onAdd, onRemove }: PathPolicyEditorProps) {
  const t = useTranslations('settings.securityPolicy');
  const [newPath, setNewPath] = useState('');

  const handleAdd = useCallback(() => {
    const trimmed = newPath.trim();
    if (!trimmed || allowedRoots.includes(trimmed)) return;
    onAdd(trimmed);
    setNewPath('');
  }, [newPath, allowedRoots, onAdd]);

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <div className="flex items-center gap-1.5">
          <IconLock className="h-3.5 w-3.5 text-destructive" />
          <span className="text-sm font-medium text-foreground">{t('forbiddenPathsLabel')}</span>
        </div>
        <p className="text-xs text-muted-foreground">{t('forbiddenPathsDesc')}</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {DEFAULT_FORBIDDEN_PATHS.map((p) => (
            <div
              key={p}
              className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-destructive/5 border border-destructive/10"
            >
              <IconLock className="h-3 w-3 text-destructive shrink-0" />
              <code className="text-xs text-destructive font-mono truncate">{p}</code>
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center gap-1.5">
          <IconFolder className="h-3.5 w-3.5 text-primary" />
          <span className="text-sm font-medium text-foreground">{t('allowedRootsLabel')}</span>
        </div>
        <p className="text-xs text-muted-foreground">{t('allowedRootsDesc')}</p>

        {allowedRoots.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {allowedRoots.map((root, idx) => (
              <div
                key={`${root}-${idx}`}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/10 border border-primary/30"
              >
                <code className="text-xs text-primary font-mono">{root}</code>
                <button
                  type="button"
                  onClick={() => onRemove(idx)}
                  className="text-primary/60 hover:text-destructive transition-colors"
                >
                  <IconX className="h-3 w-3" />
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
                handleAdd();
              }
            }}
            className="flex-1 text-sm"
          />
          <Button variant="outline" size="sm" onClick={handleAdd} disabled={!newPath.trim()}>
            <IconPlus className="h-4 w-4 mr-1" />
            {t('addPath')}
          </Button>
        </div>

        {allowedRoots.length === 0 && <p className="text-xs text-muted-foreground/70 italic">{t('noAllowedRoots')}</p>}
      </div>
    </div>
  );
}
