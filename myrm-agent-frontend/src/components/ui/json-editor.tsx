'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Textarea } from '@/components/ui/textarea';

interface JsonEditorProps {
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
  disabled?: boolean;
  className?: string;
  rows?: number;
}

export const JsonEditor = memo<JsonEditorProps>(({ value, onChange, disabled, className, rows = 6 }) => {
  const t = useTranslations('common.jsonEditor');
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setText(JSON.stringify(value, null, 2));
  }, [value]);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const raw = e.target.value;
      setText(raw);

      if (!raw.trim()) {
        setError(null);
        onChange({});
        return;
      }

      try {
        const parsed: unknown = JSON.parse(raw);
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          setError(t('mustBeObject'));
          return;
        }
        setError(null);
        onChange(parsed as Record<string, unknown>);
      } catch {
        setError(t('invalidJson'));
      }
    },
    [onChange, t],
  );

  return (
    <div className={cn('space-y-1', className)}>
      <Textarea
        value={text}
        onChange={handleChange}
        disabled={disabled}
        rows={rows}
        className={cn('font-mono text-xs resize-y', error && 'border-destructive focus-visible:ring-destructive')}
        placeholder='{ "key": "value" }'
      />
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
});

JsonEditor.displayName = 'JsonEditor';
