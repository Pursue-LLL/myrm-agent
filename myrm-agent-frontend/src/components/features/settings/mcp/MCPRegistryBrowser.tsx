import { useState, useCallback, useEffect, useRef, memo } from 'react';
import { useTranslations } from 'next-intl';
import { IconSearch, IconLoader } from '@/components/features/icons/PremiumIcons';
import { searchMCPRegistry, type MCPRegistryServer } from '@/services/llm-config';
import { MCPRegistryCard } from './MCPRegistryCard';

const DEBOUNCE_MS = 300;
const PAGE_SIZE = 20;

interface MCPRegistryBrowserProps {
  installedNames: Set<string>;
  onSelectInstall: (qualifiedName: string) => void;
}

export const MCPRegistryBrowser = memo(function MCPRegistryBrowser({
  installedNames,
  onSelectInstall,
}: MCPRegistryBrowserProps) {
  const t = useTranslations('settings');
  const [query, setQuery] = useState('');
  const [servers, setServers] = useState<MCPRegistryServer[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seqRef = useRef(0);

  const fetchPage = useCallback(
    async (searchQuery: string, pageNum: number, append: boolean) => {
      const seq = ++seqRef.current;
      setLoading(true);
      setError(null);
      try {
        const result = await searchMCPRegistry(searchQuery, pageNum, PAGE_SIZE);
        if (seq !== seqRef.current) return;
        const incoming = result.servers ?? [];
        setServers((prev) => (append ? [...prev, ...incoming] : incoming));
        setPage(result.page);
        setTotalPages(result.totalPages);
      } catch (err) {
        if (seq !== seqRef.current) return;
        setError(err instanceof Error ? err.message : t('mcpRegistryLoadFailed'));
      } finally {
        if (seq === seqRef.current) setLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void fetchPage(query, 1, false);
    }, DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, fetchPage]);

  const filteredServers = servers.filter((s) => !installedNames.has(s.qualifiedName));

  return (
    <div className="flex flex-col space-y-3">
      <div className="relative">
        <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('mcpRegistrySearchPlaceholder')}
          className="w-full rounded-lg border border-border bg-secondary px-3 py-2 pl-9 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
        />
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading && servers.length === 0 ? (
        <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
          <IconLoader className="w-4 h-4 animate-spin mr-2" />
          {t('mcpRegistryLoading')}
        </div>
      ) : filteredServers.length === 0 && !loading ? (
        <div className="text-sm text-muted-foreground py-8 text-center">
          {query ? t('mcpRegistryNoResultsFor', { query }) : t('mcpRegistryNoResults')}
        </div>
      ) : (
        <div className="space-y-2">
          {filteredServers.map((server) => (
            <MCPRegistryCard
              key={server.qualifiedName}
              server={server}
              onInstall={onSelectInstall}
            />
          ))}
        </div>
      )}

      {!loading && page < totalPages && (
        <div className="flex justify-center pt-1">
          <button
            type="button"
            onClick={() => void fetchPage(query, page + 1, true)}
            className="text-xs font-medium text-primary hover:underline"
          >
            {t('mcpRegistryLoadMore')}
          </button>
        </div>
      )}

      {loading && servers.length > 0 && (
        <div className="flex items-center justify-center py-3 text-xs text-muted-foreground">
          <IconLoader className="w-3.5 h-3.5 animate-spin mr-1.5" />
          {t('mcpRegistryLoading')}
        </div>
      )}
    </div>
  );
});
