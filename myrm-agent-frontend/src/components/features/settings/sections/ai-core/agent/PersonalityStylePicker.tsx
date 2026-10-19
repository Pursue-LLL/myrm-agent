'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import {
  Anchor,
  Cat,
  Drama,
  Eye,
  Flame,
  Heart,
  MessageCircleHeartIcon,
  Scroll,
  Smile,
  Sparkles,
  Waves,
} from 'lucide-react';

import {
  IconBook,
  IconBrain,
  IconBriefcase,
  IconGraduation,
  IconPalette,
  IconZap,
} from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { getPersonalityCatalog, type PersonalityCatalogItem } from '@/services/agent';

/** Icon component shape shared by premium SVG icons and lucide icons. */
type PersonalityIcon = React.ComponentType<{ className?: string }>;

const PERSONALITY_ICONS: Record<string, PersonalityIcon> = {
  briefcase: IconBriefcase,
  smile: Smile,
  zap: IconZap,
  book: IconBook,
  'message-heart': MessageCircleHeartIcon,
  graduation: IconGraduation,
  palette: IconPalette,
  brain: IconBrain,
  anchor: Anchor,
  drama: Drama,
  eye: Eye,
  sparkles: Sparkles,
  cat: Cat,
  flame: Flame,
  heart: Heart,
  waves: Waves,
  scroll: Scroll,
};

/** Presentation order for the categories the server ships today; others render after them. */
const KNOWN_CATEGORY_ORDER: readonly string[] = ['practical', 'fun'];

const FALLBACK_ICON: PersonalityIcon = Sparkles;

interface PersonalityStylePickerProps {
  value: string;
  onChange: (value: string) => void;
  readonly?: boolean;
}

/**
 * Communication style picker backed by the server catalog.
 *
 * Presets, descriptions and examples come from `GET /agents/personalities`, so the
 * editor keeps no second copy of the style list and a new server-side preset shows
 * up without a frontend change.
 */
export function PersonalityStylePicker({ value, onChange, readonly = false }: PersonalityStylePickerProps) {
  const t = useTranslations();
  const locale = useLocale();
  const [catalog, setCatalog] = useState<PersonalityCatalogItem[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  const prefersChinese = locale.startsWith('zh');

  useEffect(() => {
    let active = true;
    setLoadFailed(false);
    getPersonalityCatalog()
      .then((items) => {
        if (active) {
          setCatalog(items);
        }
      })
      .catch(() => {
        if (active) {
          setLoadFailed(true);
        }
      });
    return () => {
      active = false;
    };
  }, [reloadToken]);

  const handleRetry = useCallback(() => {
    setReloadToken((token) => token + 1);
  }, []);

  const labelFor = useCallback(
    (item: PersonalityCatalogItem) => {
      const key = `agent.personality.styles.${item.id}`;
      if (t.has(key)) {
        return t(key);
      }
      return prefersChinese ? item.displayNameZh : item.displayName;
    },
    [prefersChinese, t],
  );

  const categoryLabelFor = useCallback(
    (category: string) => {
      const key = `agent.personality.category.${category}`;
      return t.has(key) ? t(key) : category;
    },
    [t],
  );

  // Groups come from the catalog itself (known categories first), so a category the
  // server adds later still renders instead of silently dropping its presets.
  const groups = useMemo(() => {
    if (!catalog) {
      return [];
    }
    const order: string[] = [...KNOWN_CATEGORY_ORDER];
    for (const item of catalog) {
      if (!order.includes(item.category)) {
        order.push(item.category);
      }
    }
    return order
      .map((category) => ({ category, styles: catalog.filter((item) => item.category === category) }))
      .filter((group) => group.styles.length > 0);
  }, [catalog]);

  const selected = catalog?.find((item) => item.id === value);

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-foreground">{t('agent.personality.title')}</label>
      <p className="text-xs text-muted-foreground">{t('agent.personality.description')}</p>

      {loadFailed && (
        <div className="flex items-center gap-3 rounded-xl border border-border/40 bg-muted/20 px-3 py-2">
          <span className="text-xs text-muted-foreground">{t('agent.personality.loadFailed')}</span>
          <button
            type="button"
            onClick={handleRetry}
            className="text-xs font-medium text-primary transition-colors hover:text-primary/80"
          >
            {t('agent.personality.retry')}
          </button>
        </div>
      )}

      {!catalog &&
        !loadFailed &&
        KNOWN_CATEGORY_ORDER.map((category) => (
          <div key={category} className="space-y-1.5">
            <span className="text-xs font-medium text-muted-foreground/70">{categoryLabelFor(category)}</span>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {Array.from({ length: 4 }, (_, index) => (
                <div key={index} className="h-[74px] animate-pulse rounded-xl border border-border/40 bg-muted/20" />
              ))}
            </div>
          </div>
        ))}

      {groups.map(({ category, styles }) => {
        const categoryLabel = categoryLabelFor(category);
        return (
          <fieldset key={category} className="space-y-1.5 border-0 p-0">
            <legend className="text-xs font-medium text-muted-foreground/70">{categoryLabel}</legend>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {styles.map((item) => {
                const Icon = PERSONALITY_ICONS[item.iconId] ?? FALLBACK_ICON;
                const isSelected = value === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => !readonly && onChange(item.id)}
                    disabled={readonly}
                    aria-pressed={isSelected}
                    className={cn(
                      'flex flex-col items-center gap-1.5 p-3 rounded-xl',
                      'border transition-all duration-200',
                      readonly ? 'cursor-not-allowed opacity-70' : 'cursor-pointer',
                      isSelected
                        ? 'border-primary/40 bg-primary/5 ring-1 ring-primary/20'
                        : 'border-border/40 bg-background hover:border-border hover:bg-muted/30',
                    )}
                  >
                    <Icon className="w-5 h-5" />
                    <span
                      className={cn(
                        'text-xs font-medium leading-tight text-center',
                        isSelected ? 'text-primary' : 'text-muted-foreground',
                      )}
                    >
                      {labelFor(item)}
                    </span>
                  </button>
                );
              })}
            </div>
          </fieldset>
        );
      })}

      {selected && (
        <div className="space-y-2 rounded-xl border border-border/40 bg-muted/20 p-3">
          <p className="text-xs leading-relaxed text-muted-foreground">
            {prefersChinese ? selected.descriptionZh : selected.description}
          </p>
          <div className="space-y-1">
            <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground/70">
              {t('agent.personality.exampleLabel')}
            </span>
            <p className="whitespace-pre-wrap text-xs leading-relaxed text-foreground/90">
              {prefersChinese ? selected.exampleResponseZh : selected.exampleResponse}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
