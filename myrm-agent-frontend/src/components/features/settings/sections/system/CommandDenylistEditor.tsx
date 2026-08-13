'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconBan, IconPlus, IconX } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import SettingsSection from '../SettingsSection';

interface CommandDenylistEditorProps {
  patterns: string[];
  onAddPattern: (pattern: string) => void;
  onRemovePattern: (idx: number) => void;
}

export function CommandDenylistEditor({ patterns, onAddPattern, onRemovePattern }: CommandDenylistEditorProps) {
  const t = useTranslations('settings.securityPolicy');
  const [newPattern, setNewPattern] = useState('');

  const handleAdd = useCallback(() => {
    const trimmed = newPattern.trim();
    if (!trimmed) {return;}
    onAddPattern(trimmed);
    setNewPattern('');
  }, [newPattern, onAddPattern]);

  return (
    <SettingsSection
      title={t('commandDenylistTitle', { default: 'Command Deny List' })}
      description={t('commandDenylistDesc', {
        default:
          'Commands matching these patterns will be permanently blocked for all agents, even under YOLO mode. Uses glob syntax.',
      })}
    >
      <div className="space-y-4">
        <div className="space-y-2">
          {patterns.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {patterns.map((pattern, idx) => (
                <div
                  key={`${pattern}-${idx}`}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-destructive/10 border border-destructive/30"
                >
                  <IconBan className="h-3 w-3 text-destructive shrink-0" />
                  <code className="text-xs text-destructive font-mono">{pattern}</code>
                  <button
                    type="button"
                    onClick={() => onRemovePattern(idx)}
                    className="text-destructive/60 hover:text-destructive transition-colors"
                  >
                    <IconX className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground py-2">
              {t('noCommandDenylist', { default: 'No command restrictions configured.' })}
            </p>
          )}

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              placeholder={t('commandPatternPlaceholder', { default: 'e.g. git push --force* or *DROP DATABASE*' })}
              value={newPattern}
              onChange={(e) => setNewPattern(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleAdd();
                }
              }}
              className="flex-1 font-mono text-sm"
            />
            <Button type="button" variant="outline" size="sm" onClick={handleAdd} disabled={!newPattern.trim()}>
              <IconPlus className="h-3.5 w-3.5 mr-1" />
              {t('addCommandPattern', { default: 'Add' })}
            </Button>
          </div>
        </div>
      </div>
    </SettingsSection>
  );
}
