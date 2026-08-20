'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import { parseThemeRecipeJson, ThemeRecipeParseError, type ThemeProfileRecipe } from '@/theme-engine';

interface RecipeImportPanelProps {
  onImport: (patch: Partial<ThemeProfileRecipe>) => void;
}

const RecipeImportPanel = ({ onImport }: RecipeImportPanelProps) => {
  const t = useTranslations('settings.themeStudio.recipeImport');
  const [expanded, setExpanded] = useState(false);
  const [value, setValue] = useState('');

  const handleImport = useCallback(() => {
    try {
      const patch = parseThemeRecipeJson(value);
      onImport(patch);
      toast.success(t('success'));
      setValue('');
    } catch (error) {
      const message = error instanceof ThemeRecipeParseError ? t(`errors.${error.code}`) : t('errors.invalid_json');
      toast.error(message);
    }
  }, [onImport, t, value]);

  return (
    <div className="rounded-lg border border-border">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm"
        onClick={() => setExpanded((open) => !open)}
      >
        <span className="font-medium text-foreground">{t('title')}</span>
        {expanded ? (
          <ChevronUp className="h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
        )}
      </button>
      {expanded ? (
        <div className="space-y-2 border-t border-border px-3 pb-3 pt-2">
          <p className="text-xs text-muted-foreground">{t('hint')}</p>
          <textarea
            value={value}
            onChange={(event) => setValue(event.target.value)}
            rows={6}
            placeholder={t('placeholder')}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs"
          />
          <button
            type="button"
            disabled={!value.trim()}
            onClick={handleImport}
            className={cn(
              'rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground',
              !value.trim() && 'opacity-50',
            )}
          >
            {t('import')}
          </button>
        </div>
      ) : null}
    </div>
  );
};

export default RecipeImportPanel;
