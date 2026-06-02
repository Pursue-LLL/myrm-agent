'use client';

import { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Code } from 'lucide-react';
import { apiRequest } from '@/lib/api';

interface WorkspaceRuleItem {
  path: string;
  source: string;
  char_count: number;
  truncated: boolean;
}

interface WorkspaceRulesData {
  rules: WorkspaceRuleItem[];
  total_chars: number;
  workspace_root: string;
}

function WorkspaceRulesSection() {
  const t = useTranslations('settings.workspaceRules');
  const [data, setData] = useState<WorkspaceRulesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchRules = async () => {
      try {
        setLoading(true);
        const result = await apiRequest<WorkspaceRulesData>('/workspace/rules');
        setData(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load workspace rules');
      } finally {
        setLoading(false);
      }
    };
    fetchRules();
  }, []);

  const getSourceBadgeColor = (source: string) => {
    if (source.includes('cursor')) return 'bg-accent-warm/10 text-accent-warm border-accent-warm/20';
    if (source.includes('myrm')) return 'bg-primary/10 text-primary border-primary/20';
    if (source === 'AGENTS.md') return 'bg-primary/10 text-primary border-primary/20';
    if (source === 'CLAUDE.md') return 'bg-accent-warm/10 text-accent-warm border-accent-warm/20';
    return 'bg-muted text-muted-foreground border-border';
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold mb-2 flex items-center gap-2">
          <Code className="h-5 w-5" />
          {t('title')}
        </h2>
        <p className="text-sm text-muted-foreground">{t('description')}</p>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin h-6 w-6 border-2 border-primary border-t-transparent rounded-full" />
        </div>
      )}

      {error && (
        <div className="p-4 rounded-lg border border-destructive/30 bg-destructive/5">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      {data && !loading && (
        <>
          {data.workspace_root && (
            <div className="p-3 rounded-lg border bg-muted/30">
              <p className="text-xs text-muted-foreground">
                {t('workspaceRoot')}:{' '}
                <code className="text-xs bg-muted px-1 py-0.5 rounded">{data.workspace_root}</code>
              </p>
            </div>
          )}

          {data.rules.length === 0 ? (
            <div className="text-center py-12 space-y-3">
              <div className="mx-auto w-12 h-12 rounded-full bg-muted/50 flex items-center justify-center">
                <Code className="h-6 w-6 text-muted-foreground" />
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">{t('noRules')}</p>
                <p className="text-xs text-muted-foreground/70 mt-1">{t('noRulesHint')}</p>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">{t('loadedCount', { count: data.rules.length })}</p>
                <p className="text-xs text-muted-foreground">
                  {t('totalChars', { count: data.total_chars.toLocaleString() })}
                </p>
              </div>

              <div className="space-y-2">
                {data.rules.map((rule, idx) => (
                  <div
                    key={idx}
                    className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 p-3 rounded-lg border bg-card hover:bg-muted/30 transition-colors"
                  >
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <span
                        className={cn(
                          'inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border shrink-0',
                          getSourceBadgeColor(rule.source),
                        )}
                      >
                        {rule.source}
                      </span>
                      <span className="text-sm text-foreground truncate" title={rule.path}>
                        {rule.path.split('/').pop()}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 sm:ml-2">
                      <span className="text-xs text-muted-foreground">{rule.char_count.toLocaleString()} chars</span>
                      {rule.truncated && <span className="text-xs text-amber-500 font-medium">{t('truncated')}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default WorkspaceRulesSection;
