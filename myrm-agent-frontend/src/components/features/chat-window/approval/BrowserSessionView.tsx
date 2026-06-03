'use client';

import { useTranslations } from 'next-intl';
import { ShieldAlert, Terminal, Globe, Lock } from 'lucide-react';

interface BrowserSessionViewProps {
  action: string;
  domain: string;
  label: string;
  desc: { zh: string; en: string } | undefined;
}

export default function BrowserSessionView({ action: _action, domain, label, desc }: BrowserSessionViewProps) {
  const t = useTranslations('toolApproval');

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Lock className="h-4 w-4 text-amber-500" />
        <span className="text-sm font-medium">{t('browserSession.title')}</span>
      </div>

      <div className="space-y-2 rounded-md bg-muted/50 p-3 text-xs">
        <div className="flex items-center gap-2">
          <Globe className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="font-medium">{t('browserSession.domain')}:</span>
          <span className="font-mono text-foreground">{domain || t('browserSession.allDomains')}</span>
        </div>
        <div className="flex items-center gap-2">
          <Terminal className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="font-medium">{t('browserSession.action')}:</span>
          <span className="text-foreground">{label}</span>
        </div>
      </div>

      {desc && (
        <div className="rounded-md border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/30 p-3 text-xs">
          <div className="flex items-start gap-2">
            <ShieldAlert className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
            <div className="space-y-1">
              <p className="text-blue-900 dark:text-blue-100">{desc.zh}</p>
              <p className="text-blue-700 dark:text-blue-300 text-[10px]">{t('browserSession.storageInfo')}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
