'use client';

/**
 * Appshot 隐私黑名单编辑器：被列入的应用窗口不会进入截屏。
 */

import { memo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';

const AppshotExcludedAppsEditor = memo<{
  apps: string[];
  onChange: (apps: string[]) => void;
}>(({ apps, onChange }) => {
  const t = useTranslations('settings.system.config');
  const [inputValue, setInputValue] = useState('');

  const handleAdd = useCallback(() => {
    const val = inputValue.trim();
    if (!val || apps.includes(val)) {
      return;
    }
    onChange([...apps, val]);
    setInputValue('');
  }, [inputValue, apps, onChange]);

  const handleRemove = useCallback(
    (idx: number) => {
      onChange(apps.filter((_, i) => i !== idx));
    },
    [apps, onChange],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleAdd();
      }
    },
    [handleAdd],
  );

  return (
    <div className="space-y-2">
      <div className="space-y-1">
        <label className="text-sm font-bold text-foreground">{t('appshotPrivacyBlacklist')}</label>
        <p className="text-xs text-muted-foreground">{t('appshotPrivacyBlacklistDesc')}</p>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {apps.map((app, idx) => (
          <span
            key={`${app}-${idx}`}
            className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-destructive/10 text-destructive border border-destructive/20"
          >
            {app}
            <button
              type="button"
              onClick={() => handleRemove(idx)}
              className="ml-0.5 hover:text-destructive/80 transition-colors"
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t('appshotAddAppPlaceholder')}
          className="flex-1 px-3 py-1.5 bg-muted/50 border border-border rounded-lg text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50"
        />
        <button
          type="button"
          onClick={handleAdd}
          disabled={!inputValue.trim()}
          className="px-3 py-1.5 text-xs font-medium rounded-lg bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {t('appshotAddApp')}
        </button>
      </div>
    </div>
  );
});
AppshotExcludedAppsEditor.displayName = 'AppshotExcludedAppsEditor';

export default AppshotExcludedAppsEditor;
