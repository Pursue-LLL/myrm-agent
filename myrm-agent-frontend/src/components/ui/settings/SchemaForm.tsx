/**
 * [INPUT] '@/components/ui/switch'::Switch (POS: UI 基础组件)
 * [INPUT] '@/components/ui/input'::Input (POS: UI 基础组件)
 * [INPUT] '@/components/ui/label'::Label (POS: UI 基础组件)
 * [INPUT] '@/components/ui/select'::Select (POS: UI 基础组件)
 * [INPUT] '@/components/ui/skeleton'::Skeleton (POS: UI 基础组件)
 * [OUTPUT] SchemaForm: 动态 Schema 表单引擎，根据后端 JSON Schema 自动渲染强类型配置表单。
 * [POS] 设置页通用组件。实现 Schema-Driven UI 架构，解耦前后端配置定义。
 */
import React, { useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  matchesSchemaFilters,
  matchesSchemaVisibility,
  resolveEnumLabel,
  resolveFieldLabels,
  resolveSchemaPropertyType,
  supportsSchemaControl,
  type SchemaPropertyLike,
  type SchemaVisibilityContext,
} from '@/lib/config/schemaFormUtils';

interface JSONSchema {
  title?: string;
  description?: string;
  type: string;
  properties: Record<string, SchemaPropertyLike>;
  required?: string[];
}

interface SchemaFormProps {
  configKey: string;
  value: Record<string, unknown>;
  onChange: (newValue: Record<string, unknown>) => void;
  iconMap?: Record<string, React.ElementType>;
  translationNamespace?: string;
  /** Filter fields by backend `x-ui-section` metadata */
  section?: string;
  /** Filter fields by backend `x-ui-group` metadata (within section) */
  group?: string;
  /** Context for x-ui-visible-if / x-ui-requires-field metadata */
  visibilityContext?: SchemaVisibilityContext;
}

export const SchemaForm: React.FC<SchemaFormProps> = ({
  configKey,
  value,
  onChange,
  iconMap = {},
  translationNamespace = 'settings',
  section,
  group,
  visibilityContext,
}) => {
  const locale = useLocale();
  const t = useTranslations(translationNamespace);
  const loadFailedMessage = t('schemaForm.loadFailed');
  const [schema, setSchema] = useState<JSONSchema | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const fetchSchema = async () => {
      setLoading(true);
      try {
        const res = await fetch(`/api/v1/config/schema/${configKey}`);
        if (!res.ok) throw new Error('Failed to fetch schema');
        const data = await res.json();
        if (!cancelled) setSchema(data);
      } catch (error) {
        console.error('Schema fetch error:', error);
        if (!cancelled) toast.error(loadFailedMessage);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void fetchSchema();
    return () => {
      cancelled = true;
    };
  }, [configKey, loadFailedMessage]);

  if (loading) {
    return (
      <div className="space-y-6">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="flex items-center justify-between">
            <div className="space-y-2">
              <Skeleton className="h-4 w-[200px]" />
              <Skeleton className="h-3 w-[300px]" />
            </div>
            <Skeleton className="h-6 w-10" />
          </div>
        ))}
      </div>
    );
  }

  if (!schema || !schema.properties) {
    return <div className="text-sm text-muted-foreground">{t('schemaForm.noSchema')}</div>;
  }

  const handleChange = (key: string, val: unknown) => {
    onChange({ ...value, [key]: val });
  };

  const hasKey = (key: string) => t.has(key as Parameters<typeof t.has>[0]);
  const translate = (key: string) => t(key as Parameters<typeof t>[0]);

  return (
    <div className="space-y-4">
      {Object.entries(schema.properties)
        .filter(([, prop]) => matchesSchemaFilters(prop, { section, group }))
        .filter(([, prop]) => matchesSchemaVisibility(prop, visibilityContext))
        .map(([key, prop]) => {
          const { type, isEnum, enumValues } = resolveSchemaPropertyType(prop);

          if (!supportsSchemaControl(type, isEnum)) {
            return null;
          }

          const currentValue = value[key] !== undefined ? value[key] : prop.default;
          const { title: displayTitle, desc: displayDesc } = resolveFieldLabels(
            translate,
            hasKey,
            translationNamespace,
            key,
            prop,
            locale,
          );

          const Icon = iconMap[key];

          return (
            <div
              key={key}
              className="flex flex-col gap-3 border-b border-border/40 py-3 last:border-0 sm:flex-row sm:items-start sm:justify-between sm:gap-4"
            >
              <div className="flex items-start gap-3">
                {Icon && (
                  <div className="mt-0.5 shrink-0 rounded-lg bg-primary/10 p-2 text-primary">
                    <Icon size={18} />
                  </div>
                )}
                <div className="flex flex-col gap-1">
                  <Label className="text-sm font-medium">{displayTitle}</Label>
                  {displayDesc && <p className="text-[13px] leading-relaxed text-muted-foreground/80">{displayDesc}</p>}
                </div>
              </div>

              <div className="flex w-full items-center justify-end sm:mt-1 sm:min-w-[120px] sm:shrink-0 sm:w-auto">
                {type === 'boolean' && (
                  <Switch
                    checked={!!currentValue}
                    onCheckedChange={(checked) => handleChange(key, checked)}
                    data-testid={`config-${key}`}
                  />
                )}

                {type === 'string' && !isEnum && (
                  <Input
                    type={prop['ui:widget'] === 'password' ? 'password' : 'text'}
                    value={(currentValue as string) || ''}
                    onChange={(e) => handleChange(key, e.target.value)}
                    className="h-8 text-sm"
                    data-testid={`config-${key}`}
                  />
                )}

                {isEnum && enumValues && (
                  <Select value={(currentValue as string) || ''} onValueChange={(val) => handleChange(key, val)}>
                    <SelectTrigger className="h-8 w-[180px] text-sm" data-testid={`config-${key}`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {enumValues.map((val) => (
                        <SelectItem key={val} value={val}>
                          {resolveEnumLabel(translate, hasKey, translationNamespace, key, val)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
            </div>
          );
        })}
    </div>
  );
};
