'use client';

import { memo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Plus, X } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';

interface KeyValueEditorProps {
  value: Record<string, string>;
  onChange: (value: Record<string, string>) => void;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
  valueType?: 'text' | 'password';
  disabled?: boolean;
  className?: string;
}

export const KeyValueEditor = memo<KeyValueEditorProps>(
  ({ value, onChange, keyPlaceholder, valuePlaceholder, valueType = 'text', disabled, className }) => {
    const t = useTranslations('common.keyValueEditor');
    const entries = Object.entries(value);

    const [newKey, setNewKey] = useState('');
    const [newValue, setNewValue] = useState('');

    const handleAdd = useCallback(() => {
      const trimmedKey = newKey.trim();
      if (!trimmedKey) return;
      onChange({ ...value, [trimmedKey]: newValue });
      setNewKey('');
      setNewValue('');
    }, [newKey, newValue, value, onChange]);

    const handleRemove = useCallback(
      (key: string) => {
        const next = { ...value };
        delete next[key];
        onChange(next);
      },
      [value, onChange],
    );

    const handleValueChange = useCallback(
      (key: string, newVal: string) => {
        onChange({ ...value, [key]: newVal });
      },
      [value, onChange],
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
      <div className={cn('space-y-2', className)}>
        {entries.map(([k, v]) => (
          <div key={k} className="flex items-center gap-2">
            <Input value={k} disabled className="flex-1 font-mono text-xs bg-muted/50" />
            <Input
              value={v}
              type={valueType}
              onChange={(e) => handleValueChange(k, e.target.value)}
              disabled={disabled}
              className="flex-1 font-mono text-xs"
            />
            <Button
              variant="ghost"
              size="icon"
              onClick={() => handleRemove(k)}
              disabled={disabled}
              className="h-8 w-8 shrink-0"
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        ))}

        <div className="flex items-center gap-2">
          <Input
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={keyPlaceholder || t('keyPlaceholder')}
            disabled={disabled}
            className="flex-1 font-mono text-xs"
          />
          <Input
            value={newValue}
            type={valueType}
            onChange={(e) => setNewValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={valuePlaceholder || t('valuePlaceholder')}
            disabled={disabled}
            className="flex-1 font-mono text-xs"
          />
          <Button
            variant="outline"
            size="icon"
            onClick={handleAdd}
            disabled={disabled || !newKey.trim()}
            className="h-8 w-8 shrink-0"
          >
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    );
  },
);

KeyValueEditor.displayName = 'KeyValueEditor';
