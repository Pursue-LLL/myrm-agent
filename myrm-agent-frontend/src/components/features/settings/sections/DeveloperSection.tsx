'use client';

import { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Switch } from '@/components/primitives/switch';
import { Label } from '@/components/primitives/label';
import { IconCode, IconAlertCircle } from '@/components/features/icons/PremiumIcons';

import dynamic from 'next/dynamic';
import { EvaluationSection } from './EvaluationSection';

const ExternalAgentsConfig = dynamic(() => import('./ExternalAgentsConfig'));

function DeveloperSection() {
  const t = useTranslations('settings.developer');
  const [showSystemMessages, setShowSystemMessages] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem('developer_show_system_messages');
    setShowSystemMessages(stored === 'true');
  }, []);

  const handleToggle = (checked: boolean) => {
    localStorage.setItem('developer_show_system_messages', String(checked));
    setShowSystemMessages(checked);

    window.dispatchEvent(
      new CustomEvent('developer-mode-changed', {
        detail: { showSystemMessages: checked },
      }),
    );
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <IconCode className="h-5 w-5" />
          {t('title')}
        </h2>
        <p className="text-sm text-muted-foreground mb-6">{t('description')}</p>
      </div>

      <div className="space-y-4">
        {/* Show System Messages Toggle */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 p-4 border rounded-lg">
          <div className="space-y-1 flex-1">
            <div className="flex items-center gap-2">
              <Label htmlFor="show-system-messages" className="text-base font-medium">
                {t('showSystemMessages')}
              </Label>
            </div>
            <p className="text-sm text-muted-foreground">{t('showSystemMessagesDesc')}</p>

            {showSystemMessages && (
              <div className="flex items-start gap-2 mt-2 p-2 bg-yellow-50 dark:bg-yellow-900/20 rounded-md">
                <IconAlertCircle className="h-4 w-4 text-yellow-600 dark:text-yellow-400 mt-0.5 flex-shrink-0" />
                <p className="text-xs text-yellow-700 dark:text-yellow-300">{t('showSystemMessagesWarning')}</p>
              </div>
            )}
          </div>
          <Switch id="show-system-messages" checked={showSystemMessages} onCheckedChange={handleToggle} />
        </div>
      </div>

      <div className="border-t border-border/50" />

      <ExternalAgentsConfig />

      <div className="border-t border-border/50" />

      <EvaluationSection />
    </div>
  );
}

export default DeveloperSection;
