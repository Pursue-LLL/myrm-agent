'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconGlobe, IconPlus, IconX } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Switch } from '@/components/primitives/switch';
import SettingsSection from '../SettingsSection';

interface DomainAllowlistEditorProps {
  domains: string[];
  hitlEnabled: boolean;
  onAddDomain: (domain: string) => void;
  onRemoveDomain: (idx: number) => void;
  onHitlToggle: (checked: boolean) => void;
}

export function DomainAllowlistEditor({
  domains,
  hitlEnabled,
  onAddDomain,
  onRemoveDomain,
  onHitlToggle,
}: DomainAllowlistEditorProps) {
  const t = useTranslations('settings.securityPolicy.domainAllowlist');
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
        <div className="flex items-center justify-between">
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-foreground">{t('hitlLabel')}</label>
            <p className="text-xs text-muted-foreground">{t('hitlDesc')}</p>
          </div>
          <Switch checked={hitlEnabled} onCheckedChange={onHitlToggle} />
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <IconGlobe className="h-3.5 w-3.5 text-primary" />
            <span className="text-sm font-medium text-foreground">{t('listLabel')}</span>
          </div>
          <p className="text-xs text-muted-foreground">{t('listDesc')}</p>

          {domains.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {domains.map((domain, idx) => (
                <div
                  key={`${domain}-${idx}`}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/10 border border-primary/30"
                >
                  <code className="text-xs text-primary font-mono">{domain}</code>
                  <button
                    type="button"
                    onClick={() => onRemoveDomain(idx)}
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
              placeholder={t('placeholder')}
              value={newDomain}
              onChange={(e) => setNewDomain(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleAdd();
                }
              }}
              className="flex-1 text-sm"
            />
            <Button variant="outline" size="sm" onClick={handleAdd} disabled={!newDomain.trim()}>
              <IconPlus className="h-4 w-4 mr-1" />
              {t('addDomain')}
            </Button>
          </div>

          {domains.length === 0 && <p className="text-xs text-muted-foreground/70 italic">{t('empty')}</p>}
        </div>
      </div>
    </SettingsSection>
  );
}
