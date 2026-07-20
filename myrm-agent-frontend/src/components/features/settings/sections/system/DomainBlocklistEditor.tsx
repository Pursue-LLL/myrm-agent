'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconBan, IconPlus, IconX } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import SettingsSection from '../SettingsSection';

interface DomainBlocklistEditorProps {
  domains: string[];
  onAddDomain: (domain: string) => void;
  onRemoveDomain: (idx: number) => void;
}

export function DomainBlocklistEditor({ domains, onAddDomain, onRemoveDomain }: DomainBlocklistEditorProps) {
  const t = useTranslations('settings.securityPolicy.domainBlocklist');
  const [newDomain, setNewDomain] = useState('');

  const handleAdd = useCallback(() => {
    const trimmed = newDomain.trim();
    if (!trimmed) return;
    onAddDomain(trimmed);
    setNewDomain('');
  }, [newDomain, onAddDomain]);

  return (
    <SettingsSection title={t('title')} description={t('description')}>
      <div className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <IconBan className="h-3.5 w-3.5 text-destructive" />
            <span className="text-sm font-medium text-foreground">{t('listLabel')}</span>
          </div>
          <p className="text-xs text-muted-foreground">{t('listDesc')}</p>

          {domains.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {domains.map((domain, idx) => (
                <div
                  key={`${domain}-${idx}`}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-destructive/10 border border-destructive/30"
                >
                  <code className="text-xs text-destructive font-mono">{domain}</code>
                  <button
                    type="button"
                    onClick={() => onRemoveDomain(idx)}
                    className="text-destructive/60 hover:text-destructive transition-colors"
                  >
                    <IconX className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-center gap-2">
            <Input
              placeholder={t('placeholder')}
              value={newDomain}
              onChange={(e) => setNewDomain(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleAdd();
                }
              }}
              className="max-w-md"
            />
            <Button type="button" variant="outline" size="sm" onClick={handleAdd} disabled={!newDomain.trim()}>
              <IconPlus className="h-3.5 w-3.5 mr-1" />
              {t('add')}
            </Button>
          </div>
        </div>
      </div>
    </SettingsSection>
  );
}
