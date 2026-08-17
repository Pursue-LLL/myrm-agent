'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Textarea } from '@/components/primitives/textarea';
import { Label } from '@/components/primitives/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import {
  getMemories,
  createMemory as apiCreateMemory,
  deleteMemory as apiDeleteMemory,
  type Memory,
} from '@/services/memory';
import {
  BRAND_FIELD_KEYS,
  brandProfileKey,
  isBrandProfileKey,
  isColorField,
  isLongTextField,
  toBrandEntries,
  validateBrandField,
  type BrandEntry,
  type BrandFieldKey,
  type BrandValues,
} from './brandSchema';
import { IconPalette, IconTrash } from '@/components/features/icons/PremiumIcons';

interface RowState {
  field: BrandFieldKey;
  value: string;
  error: string | null;
}

function createRows(entries: BrandEntry[]): RowState[] {
  const byField = new Map(entries.map((e) => [e.field, e.value]));
  return BRAND_FIELD_KEYS.map((field) => ({
    field,
    value: byField.get(field) ?? '',
    error: null,
  }));
}

function buildPatch(rows: RowState[]): { toSave: Record<string, string>; toDelete: string[] } {
  const toSave: Record<string, string> = {};
  const toDelete: string[] = [];
  for (const row of rows) {
    const key = brandProfileKey(row.field);
    const trimmed = row.value.trim();
    if (trimmed) {
      toSave[key] = trimmed;
    } else {
      toDelete.push(key);
    }
  }
  return { toSave, toDelete };
}

const BrandStudioSection = () => {
  const t = useTranslations('brandStudio');

  const [rows, setRows] = useState<RowState[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const loadBrandEntries = useCallback(async () => {
    setLoading(true);
    try {
      const response = await getMemories({ type: 'profile', page: 1, pageSize: 100, sortOrder: 'asc' });
      const brandMemories = response.items.filter((m: Memory) => isBrandProfileKey(m.key));
      setRows(createRows(toBrandEntries(brandMemories)));
    } catch {
      setRows(createRows([]));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadBrandEntries();
  }, [loadBrandEntries]);

  const preview: BrandValues = useMemo(() => {
    const values: BrandValues = {};
    for (const row of rows) {
      const trimmed = row.value.trim();
      if (trimmed) {values[row.field] = trimmed;}
    }
    return values;
  }, [rows]);

  const hasValue = rows.some((r) => r.value.trim().length > 0);

  const updateRow = useCallback((field: BrandFieldKey, value: string) => {
    setRows((prev) => prev.map((r) => (r.field === field ? { ...r, value, error: null } : r)));
  }, []);

  const validateAll = useCallback((): boolean => {
    let valid = true;
    const next = rows.map((r) => {
      if (!r.value.trim()) {return r;}
      const error = validateBrandField(r.field, r.value);
      if (error) {valid = false;}
      return { ...r, error };
    });
    setRows(next);
    return valid;
  }, [rows]);

  const handleSave = useCallback(async () => {
    if (!validateAll()) {
      toast.error(t('invalidFields'));
      return;
    }
    setSaving(true);
    try {
      const { toSave, toDelete } = buildPatch(rows);
      for (const key of toDelete) {
        await apiDeleteMemory(key, 'profile').catch(() => undefined);
      }
      for (const [key, value] of Object.entries(toSave)) {
        await apiCreateMemory({
          memory_type: 'profile',
          content: `${key}: ${value}`,
          key,
          value,
        });
      }
      await loadBrandEntries();
      toast.success(t('saveSuccess'));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save brand style';
      toast.error(message);
    } finally {
      setSaving(false);
    }
  }, [rows, validateAll, loadBrandEntries, t]);

  const resetForm = useCallback(() => {
    setRows(createRows([]));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">{t('title')}</h1>
        <p className="text-sm text-muted-foreground">{t('subtitle')}</p>
      </div>

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle className="text-base font-semibold">{t('previewTitle')}</CardTitle>
          <CardDescription>{t('previewDescription')}</CardDescription>
        </CardHeader>
        <CardContent>
          <BrandPreview values={preview} hasValue={hasValue} />
        </CardContent>
      </Card>

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle className="text-base font-semibold">{t('fieldsTitle')}</CardTitle>
          <CardDescription>{t('fieldsDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {loading ? (
            <div className="text-sm text-muted-foreground">{t('loading')}</div>
          ) : (
            rows.map((row) => (
              <div key={row.field} className="grid grid-cols-1 gap-2 sm:grid-cols-[200px_1fr] sm:items-center">
                <Label className="text-sm text-muted-foreground">{t(`fields.${row.field}`)}</Label>
                {isColorField(row.field) ? (
                  <ColorField
                    value={row.value}
                    error={row.error}
                    ariaLabel={t(`fields.${row.field}`)}
                    onChange={(value) => updateRow(row.field, value)}
                  />
                ) : isLongTextField(row.field) ? (
                  <Textarea
                    value={row.value}
                    rows={2}
                    placeholder={t(`placeholders.${row.field}`)}
                    onChange={(e) => updateRow(row.field, e.target.value)}
                  />
                ) : (
                  <Input
                    value={row.value}
                    placeholder={t(`placeholders.${row.field}`)}
                    onChange={(e) => updateRow(row.field, e.target.value)}
                  />
                )}
                {row.error && <p className="text-xs text-destructive sm:col-start-2">{t(`errors.${row.error}`)}</p>}
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={handleSave} disabled={saving} className="gap-1.5">
          <IconPalette className="h-4 w-4" />
          {saving ? t('saving') : t('save')}
        </Button>
        <Button variant="outline" onClick={resetForm} className="gap-1.5">
          <IconTrash className="h-4 w-4" />
          {t('reset')}
        </Button>
      </div>
    </div>
  );
};

function ColorField({
  value,
  error,
  ariaLabel,
  onChange,
}: {
  value: string;
  error: string | null;
  ariaLabel: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <span
        className={cn(
          'relative inline-flex h-8 w-8 shrink-0 overflow-hidden rounded-md border border-border/60',
          !value && 'bg-muted',
        )}
      >
        {value ? (
          <span className="h-full w-full" style={{ backgroundColor: value }} />
        ) : null}
        <input
          type="color"
          value={/^#[0-9a-fA-F]{6}$/.test(value) ? value : '#000000'}
          onChange={(e) => onChange(e.target.value)}
          className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
          aria-label={ariaLabel}
        />
      </span>
      <Input
        value={value}
        placeholder="#6C5CE7"
        onChange={(e) => onChange(e.target.value)}
        className={cn(error && 'border-destructive')}
      />
    </div>
  );
}

function BrandPreview({ values, hasValue }: { values: BrandValues; hasValue: boolean }) {
  const t = useTranslations('brandStudio');
  const primary = values.primary_color || '#6C5CE7';
  const secondary = values.secondary_color || '#1E1B4B';
  const accent = values.accent_color || '#10B981';
  const name = values.name || t('previewFallbackName');
  const tagline = values.tagline || t('previewFallbackTagline');
  const font = values.font || t('previewFallbackFont');

  if (!hasValue) {
    return <p className="text-sm text-muted-foreground">{t('previewEmpty')}</p>;
  }

  return (
    <div className="rounded-xl border border-border/60 p-4 sm:p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1.5">
          <p className="text-lg font-bold" style={{ fontFamily: font }}>
            {name}
          </p>
          <p className="text-sm text-muted-foreground">{tagline}</p>
          <p className="text-xs text-muted-foreground">{t('previewFont', { font })}</p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="h-8 w-8 rounded-full border border-border/60"
            style={{ backgroundColor: primary }}
            title={t('previewPrimary')}
          />
          <span
            className="h-8 w-8 rounded-full border border-border/60"
            style={{ backgroundColor: secondary }}
            title={t('previewSecondary')}
          />
          <span
            className="h-8 w-8 rounded-full border border-border/60"
            style={{ backgroundColor: accent }}
            title={t('previewAccent')}
          />
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          size="sm"
          className="pointer-events-none"
          style={{ backgroundColor: primary }}
        >
          {t('previewPrimary')}
        </Button>
        <Button size="sm" variant="outline" className="pointer-events-none">
          {t('previewSecondary')}
        </Button>
        <Button
          size="sm"
          className="pointer-events-none text-white"
          style={{ backgroundColor: accent }}
        >
          {t('previewAccent')}
        </Button>
      </div>
    </div>
  );
}

BrandStudioSection.displayName = 'BrandStudioSection';

export default BrandStudioSection;
