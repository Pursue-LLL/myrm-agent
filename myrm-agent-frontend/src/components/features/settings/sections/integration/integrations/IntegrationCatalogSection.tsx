'use client';

import { memo, useState, useCallback, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Input } from '@/components/primitives/input';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Skeleton } from '@/components/primitives/skeleton';
import { IconArrowRight } from '@/components/features/icons/PremiumIcons';
import { apiRequest } from '@/lib/api';
import { IconSearch, IconExternalLink } from './catalog-icons';
import SettingsSection from '../../SettingsSection';
import { CatalogConnectionStatus } from './CatalogConnectionStatus';
import { IntegrationConnectDialog } from './IntegrationConnectDialog';
import { SERVICE_ICONS } from './service-icons';
import { LifecycleWebhookSection } from './LifecycleWebhookSection';
import { A2APeerRegistrySection } from './A2APeerRegistrySection';
import { useCatalogConnectionState, type CatalogConnectionState } from './catalog-connection';
import { useCatalogLocale } from './catalog-locale';
import type { CatalogEntry, CatalogResponse } from './catalog-types';

const IntegrationCatalogSection = memo(() => {
  const t = useTranslations('settings.integrationCatalog');
  const locale = useCatalogLocale();
  const resolveConnectionState = useCatalogConnectionState();
  const [allEntries, setAllEntries] = useState<CatalogEntry[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [connectEntry, setConnectEntry] = useState<CatalogEntry | null>(null);

  const fetchCatalog = useCallback(async () => {
    try {
      const data = await apiRequest<CatalogResponse>('/integrations/catalog', { silent: true });
      setAllEntries(data.entries);
      setCategories(data.categories);
    } catch {
      // Silently fail - catalog is optional UX enhancement
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCatalog();
  }, [fetchCatalog]);

  const entries = useMemo(() => {
    let filtered = allEntries;
    if (activeCategory) {
      filtered = filtered.filter((e) => e.category === activeCategory);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (e) =>
          e.name.toLowerCase().includes(q) ||
          e.nameZh.toLowerCase().includes(q) ||
          e.description.toLowerCase().includes(q) ||
          e.descriptionZh.toLowerCase().includes(q) ||
          e.tags.some((tag) => tag.toLowerCase().includes(q)),
      );
    }
    return filtered;
  }, [allEntries, activeCategory, searchQuery]);

  const getName = useCallback(
    (entry: CatalogEntry) => (locale === 'zh' && entry.nameZh ? entry.nameZh : entry.name),
    [locale],
  );

  const getDescription = useCallback(
    (entry: CatalogEntry) => (locale === 'zh' && entry.descriptionZh ? entry.descriptionZh : entry.description),
    [locale],
  );

  if (loading) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-10 w-full" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <SettingsSection title={t('title')} description={t('description')}>
        {/* Search + Category filters */}
        <div className="mb-6 space-y-4">
          <div className="relative">
            <IconSearch className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('searchPlaceholder')}
              className="pl-9"
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Badge
              variant={activeCategory === null ? 'default' : 'outline'}
              className="cursor-pointer transition-colors"
              onClick={() => setActiveCategory(null)}
            >
              {t('allCategories')}
            </Badge>
            {categories.map((cat) => (
              <Badge
                key={cat}
                variant={activeCategory === cat ? 'default' : 'outline'}
                className="cursor-pointer transition-colors"
                onClick={() => setActiveCategory(cat)}
              >
                {t.has(`categories.${cat}`) ? t(`categories.${cat}`) : cat}
              </Badge>
            ))}
          </div>
        </div>

        {/* Service cards grid */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {entries.map((entry) => (
            <IntegrationCard
              key={entry.id}
              entry={entry}
              connectionState={resolveConnectionState(entry)}
              getName={getName}
              getDescription={getDescription}
              onConnect={setConnectEntry}
            />
          ))}
        </div>

        {entries.length === 0 && (
          <div className="text-muted-foreground py-12 text-center text-sm">{t('noResults')}</div>
        )}

        {/* Custom integration link & Lifecycle Outbound Webhooks */}
        <div className="border-border mt-6 border-t pt-4">
          <p className="text-muted-foreground text-sm">{t('customIntegrationHint')}</p>
        </div>

        <LifecycleWebhookSection />
        <A2APeerRegistrySection />
      </SettingsSection>

      {/* Connect Dialog */}
      {connectEntry && (
        <IntegrationConnectDialog
          entry={connectEntry}
          locale={locale}
          onClose={() => setConnectEntry(null)}
          onConnected={() => setConnectEntry(null)}
        />
      )}
    </div>
  );
});

IntegrationCatalogSection.displayName = 'IntegrationCatalogSection';

export default IntegrationCatalogSection;

// --- IntegrationCard sub-component ---

interface IntegrationCardProps {
  entry: CatalogEntry;
  connectionState: CatalogConnectionState;
  getName: (entry: CatalogEntry) => string;
  getDescription: (entry: CatalogEntry) => string;
  onConnect: (entry: CatalogEntry) => void;
}

const IntegrationCard = memo<IntegrationCardProps>(({ entry, connectionState, getName, getDescription, onConnect }) => {
  const t = useTranslations('settings.integrationCatalog');
  const IconComponent = SERVICE_ICONS[entry.icon];
  const name = getName(entry);

  return (
    <div className="border-border bg-card hover:border-primary/30 group relative flex flex-col rounded-xl border p-4 transition-all">
      <div className="mb-3 flex items-start justify-between">
        <div className="bg-muted flex h-10 w-10 items-center justify-center rounded-lg">
          {IconComponent ? (
            <IconComponent className="h-5 w-5" />
          ) : (
            <span className="text-muted-foreground text-xs font-medium">{entry.name.slice(0, 2).toUpperCase()}</span>
          )}
        </div>
        {entry.website && (
          // Hover-capable pointers reveal the link on hover or keyboard focus; touch screens always show it.
          <a
            href={entry.website}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={t('openWebsite', { name })}
            className="text-muted-foreground hover:text-foreground -m-1.5 p-1.5 transition-opacity [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-focus-within:opacity-100 [@media(hover:hover)]:group-hover:opacity-100"
          >
            <IconExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
      </div>

      <h4 className="text-foreground mb-1 text-sm font-medium">{name}</h4>
      <p className="text-muted-foreground mb-4 line-clamp-2 flex-1 text-xs">{getDescription(entry)}</p>

      {connectionState === 'available' ? (
        <Button size="sm" variant="outline" className="w-full" onClick={() => onConnect(entry)}>
          {t('connect')}
        </Button>
      ) : (
        <div className="flex h-8 items-center justify-between gap-2">
          <CatalogConnectionStatus state={connectionState} />
          <Link
            href="/settings/mcp"
            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium transition-colors"
          >
            {t('manage')}
            <IconArrowRight className="h-3 w-3" />
          </Link>
        </div>
      )}
    </div>
  );
});

IntegrationCard.displayName = 'IntegrationCard';
