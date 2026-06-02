'use client';

import { memo, useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { IconAlertCircle } from '@/components/ui/icons/PremiumIcons';

interface ModelKwargsEditorProps {
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
  label: string;
}

const ModelKwargsEditor = memo<ModelKwargsEditorProps>(({ value, onChange, label }) => {
  const t = useTranslations('settings.defaultModel');
  const tSettings = useTranslations('settings');
  const [text, setText] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    setText(JSON.stringify(value, null, 2));
  }, [value]);

  const handleBlur = () => {
    try {
      const parsed = JSON.parse(text || '{}');
      onChange(parsed);
      setError('');
    } catch {
      setError(t('invalidJson'));
    }
  };

  const handleFormat = () => {
    try {
      const parsed = JSON.parse(text || '{}');
      setText(JSON.stringify(parsed, null, 2));
      setError('');
    } catch {
      setError(t('invalidJson'));
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-foreground">{label}</label>
        <button onClick={handleFormat} className="text-xs text-primary hover:underline">
          {t('formatJson')}
        </button>
      </div>
      <textarea
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setError('');
        }}
        onBlur={handleBlur}
        placeholder={tSettings('modelKwargsPlaceholder')}
        rows={4}
        className={cn(
          'w-full px-3 py-2.5 text-sm font-mono bg-secondary/50 border rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-primary/30',
          error ? 'border-destructive' : 'border-border',
        )}
      />
      {error && (
        <div className="flex items-center gap-1.5 text-xs text-destructive">
          <IconAlertCircle className="w-3 h-3" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
});

ModelKwargsEditor.displayName = 'ModelKwargsEditor';

export default ModelKwargsEditor;
