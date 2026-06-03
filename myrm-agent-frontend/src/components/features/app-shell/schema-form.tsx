'use client';

import { memo, useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { RotateCcw } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Switch } from '@/components/primitives/switch';
import { Textarea } from '@/components/primitives/textarea';
import { Button } from '@/components/primitives/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';

type ConfigValue = string | number | boolean | null;

interface PropertySchema {
  type?: string;
  title?: string;
  description?: string;
  default?: ConfigValue;
  enum?: ConfigValue[];
  format?: string;
  minimum?: number;
  maximum?: number;
}

interface JsonSchema {
  type?: string;
  properties?: Record<string, PropertySchema>;
  required?: string[];
}

interface SchemaFormProps {
  schema: JsonSchema;
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
  disabled?: boolean;
  className?: string;
}

function renderField(
  key: string,
  prop: PropertySchema,
  currentValue: unknown,
  isRequired: boolean,
  disabled: boolean,
  showError: boolean,
  onFieldChange: (key: string, val: ConfigValue) => void,
  onFieldBlur: (key: string) => void,
  requiredErrorText: string,
) {
  const label = prop.title || key;
  const val = currentValue ?? prop.default ?? null;
  const isEmpty = val === null || val === '' || val === undefined;
  const hasError = showError && isRequired && isEmpty;
  const errorBorder = hasError ? 'border-destructive focus-visible:ring-destructive' : '';

  if (prop.enum && Array.isArray(prop.enum)) {
    return (
      <div key={key} className="space-y-1.5">
        <Label className="text-sm font-medium">
          {label}
          {isRequired && <span className="text-destructive ml-0.5">*</span>}
        </Label>
        {prop.description && <p className="text-xs text-muted-foreground">{prop.description}</p>}
        <Select
          value={val != null ? String(val) : undefined}
          onValueChange={(v) => {
            onFieldChange(key, v);
            onFieldBlur(key);
          }}
          disabled={disabled}
        >
          <SelectTrigger className={cn('h-9', errorBorder)}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {prop.enum.map((opt) => (
              <SelectItem key={String(opt)} value={String(opt)}>
                {String(opt)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {hasError && <p className="text-xs text-destructive">{requiredErrorText}</p>}
      </div>
    );
  }

  switch (prop.type) {
    case 'boolean':
      return (
        <div key={key} className="flex items-center justify-between py-1">
          <div className="space-y-0.5">
            <Label className="text-sm font-medium">{label}</Label>
            {prop.description && <p className="text-xs text-muted-foreground">{prop.description}</p>}
          </div>
          <Switch
            checked={typeof val === 'boolean' ? val : false}
            onCheckedChange={(checked) => onFieldChange(key, checked)}
            disabled={disabled}
          />
        </div>
      );

    case 'integer':
    case 'number':
      return (
        <div key={key} className="space-y-1.5">
          <Label className="text-sm font-medium">
            {label}
            {isRequired && <span className="text-destructive ml-0.5">*</span>}
          </Label>
          {prop.description && <p className="text-xs text-muted-foreground">{prop.description}</p>}
          <Input
            type="number"
            value={val != null ? String(val) : ''}
            onChange={(e) => {
              const raw = e.target.value;
              if (raw === '') {
                onFieldChange(key, null);
                return;
              }
              const num = prop.type === 'integer' ? parseInt(raw, 10) : parseFloat(raw);
              if (!isNaN(num)) onFieldChange(key, num);
            }}
            onBlur={() => onFieldBlur(key)}
            min={prop.minimum}
            max={prop.maximum}
            disabled={disabled}
            className={cn('font-mono text-xs', errorBorder)}
          />
          {hasError && <p className="text-xs text-destructive">{requiredErrorText}</p>}
        </div>
      );

    default: {
      const isPassword = prop.format === 'password';
      const isTextarea = prop.format === 'textarea';

      if (isTextarea) {
        return (
          <div key={key} className="space-y-1.5">
            <Label className="text-sm font-medium">
              {label}
              {isRequired && <span className="text-destructive ml-0.5">*</span>}
            </Label>
            {prop.description && <p className="text-xs text-muted-foreground">{prop.description}</p>}
            <Textarea
              value={typeof val === 'string' ? val : ''}
              onChange={(e) => onFieldChange(key, e.target.value)}
              onBlur={() => onFieldBlur(key)}
              disabled={disabled}
              rows={4}
              className={cn('font-mono text-xs resize-y', errorBorder)}
            />
            {hasError && <p className="text-xs text-destructive">{requiredErrorText}</p>}
          </div>
        );
      }

      return (
        <div key={key} className="space-y-1.5">
          <Label className="text-sm font-medium">
            {label}
            {isRequired && <span className="text-destructive ml-0.5">*</span>}
          </Label>
          {prop.description && <p className="text-xs text-muted-foreground">{prop.description}</p>}
          <Input
            type={isPassword ? 'password' : 'text'}
            value={typeof val === 'string' ? val : ''}
            onChange={(e) => onFieldChange(key, e.target.value)}
            onBlur={() => onFieldBlur(key)}
            disabled={disabled}
            className={cn('font-mono text-xs', errorBorder)}
          />
          {hasError && <p className="text-xs text-destructive">{requiredErrorText}</p>}
        </div>
      );
    }
  }
}

export const SchemaForm = memo<SchemaFormProps>(({ schema, value, onChange, disabled, className }) => {
  const t = useTranslations('common.schemaForm');
  const properties = schema.properties || {};
  const requiredFields = new Set(schema.required || []);
  const [touched, setTouched] = useState<Set<string>>(new Set());

  const handleFieldChange = useCallback(
    (key: string, val: ConfigValue) => {
      const next = { ...value };
      if (val === null || val === '') {
        delete next[key];
      } else {
        next[key] = val;
      }
      onChange(next);
    },
    [value, onChange],
  );

  const handleFieldBlur = useCallback((key: string) => {
    setTouched((prev) => {
      if (prev.has(key)) return prev;
      const next = new Set(prev);
      next.add(key);
      return next;
    });
  }, []);

  const handleReset = useCallback(() => {
    const defaults: Record<string, unknown> = {};
    for (const [key, prop] of Object.entries(properties)) {
      if (prop.default !== undefined) {
        defaults[key] = prop.default;
      }
    }
    onChange(defaults);
    setTouched(new Set());
  }, [properties, onChange]);

  const hasDefaults = Object.values(properties).some((p) => p.default !== undefined);
  const propEntries = Object.entries(properties);

  if (propEntries.length === 0) return null;

  return (
    <div className={cn('space-y-4', className)}>
      {propEntries.map(([key, prop]) =>
        renderField(
          key,
          prop,
          value[key],
          requiredFields.has(key),
          !!disabled,
          touched.has(key),
          handleFieldChange,
          handleFieldBlur,
          t('requiredField'),
        ),
      )}
      {hasDefaults && (
        <Button variant="ghost" size="sm" onClick={handleReset} disabled={disabled} className="text-xs">
          <RotateCcw className="mr-1.5 h-3 w-3" />
          {t('resetDefaults')}
        </Button>
      )}
    </div>
  );
});

SchemaForm.displayName = 'SchemaForm';
