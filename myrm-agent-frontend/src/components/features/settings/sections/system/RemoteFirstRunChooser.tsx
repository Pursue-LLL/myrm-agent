'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';

interface RemoteFirstRunChooserProps {
  onSelectLocal: () => void;
  onSelectRemote: () => void;
  onSelectCloud: () => void;
}

const RemoteFirstRunChooser = memo(({ onSelectLocal, onSelectRemote, onSelectCloud }: RemoteFirstRunChooserProps) => {
  const t = useTranslations('settings.system.serverConnection');

  return (
    <div className="space-y-3 rounded-2xl border border-indigo-500/30 bg-indigo-500/5 p-4">
      <p className="text-sm font-bold text-foreground">{t('wizardTitle')}</p>
      <p className="text-xs text-muted-foreground leading-relaxed">{t('wizardDesc')}</p>
      <div className="grid gap-2 sm:grid-cols-3">
        <button
          type="button"
          onClick={onSelectLocal}
          className="px-3 py-2.5 rounded-xl border border-white/10 text-xs font-bold hover:bg-white/5 transition-colors"
        >
          {t('optLocal')}
        </button>
        <button
          type="button"
          onClick={onSelectRemote}
          className="px-3 py-2.5 rounded-xl border border-white/10 text-xs font-bold hover:bg-white/5 transition-colors"
        >
          {t('optRemote')}
        </button>
        <button
          type="button"
          onClick={onSelectCloud}
          className="px-3 py-2.5 rounded-xl bg-indigo-500 text-white text-xs font-bold hover:bg-indigo-600 transition-colors"
        >
          {t('optCloud')}
        </button>
      </div>
    </div>
  );
});

RemoteFirstRunChooser.displayName = 'RemoteFirstRunChooser';
export default RemoteFirstRunChooser;
