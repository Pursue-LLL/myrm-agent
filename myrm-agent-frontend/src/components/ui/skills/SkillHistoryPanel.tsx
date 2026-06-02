'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { formatDistanceToNow } from 'date-fns';
import { zhCN, enUS } from 'date-fns/locale';
import { RefreshCw, Undo2, CheckCircle2, XCircle, FileClock, History } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from '@/hooks/useToast';
import { useTheme } from 'next-themes';
import { LazyMonacoDiffEditor as DiffEditor } from '@/components/ui/lazy-monaco-editor';

interface EvolutionRecord {
  id: string;
  skill_id: string;
  skill_name: string;
  evolution_type: string;
  reason: string;
  original_content: string;
  evolved_content: string;
  confidence: number;
  test_passed: boolean;
  status: 'approved' | 'rejected' | 'rolled_back';
  created_at: string;
  resolved_at: string | null;
}

export function SkillHistoryPanel({ className }: { className?: string }) {
  const t = useTranslations('settings.skills.history');
  const [records, setRecords] = useState<EvolutionRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [isRollingBack, setIsRollingBack] = useState<string | null>(null);
  const { theme } = useTheme();

  // Using English as default locale for date formatting if not zh
  const locale = t('locale') === 'zh' ? zhCN : enUS;

  const fetchHistory = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await fetch('/api/evolution/history?limit=20');
      if (!res.ok) throw new Error('Failed to fetch history');
      const data = await res.json();
      setRecords(data.items || []);
    } catch {
      toast({ title: t('fetchError'), variant: 'destructive' });
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const handleRollback = async (id: string, skillName: string) => {
    if (!window.confirm(t('confirmRollback', { name: skillName }))) return;

    setIsRollingBack(id);
    try {
      const res = await fetch(`/api/v1/evolution/history/${id}/rollback`, {
        method: 'POST',
      });
      if (!res.ok) {
        throw new Error('Rollback failed');
      }
      toast({ title: t('rollbackSuccess', { name: skillName }) });
      await fetchHistory();
    } catch {
      toast({ title: t('rollbackFailed', { name: skillName }), variant: 'destructive' });
    } finally {
      setIsRollingBack(null);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'approved':
        return <CheckCircle2 className="h-4 w-4 text-green-500" />;
      case 'rejected':
        return <XCircle className="h-4 w-4 text-red-500" />;
      case 'rolled_back':
        return <Undo2 className="h-4 w-4 text-yellow-500" />;
      default:
        return <FileClock className="h-4 w-4 text-muted-foreground" />;
    }
  };

  return (
    <div className={cn('rounded-xl border bg-card/50', className)}>
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-primary/10 rounded-full">
            <History className="h-4 w-4 text-primary" />
          </div>
          <h3 className="font-semibold">{t('title')}</h3>
          <Badge variant="secondary" className="ml-2 px-1.5 py-0 text-xs">
            {records.length}
          </Badge>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={fetchHistory}
          disabled={isLoading}
          className="h-8 w-8 p-0"
          title={t('refresh')}
        >
          <RefreshCw className={cn('h-4 w-4 text-muted-foreground', isLoading && 'animate-spin')} />
        </Button>
      </div>

      {isLoading && records.length === 0 ? (
        <div className="p-8 text-center text-sm text-muted-foreground">{t('loading')}</div>
      ) : records.length === 0 ? (
        <div className="p-8 text-center text-sm text-muted-foreground">{t('empty')}</div>
      ) : (
        <div className="divide-y divide-border/50 max-h-[500px] overflow-y-auto">
          {records.map((record) => {
            const isExpanded = expandedId === record.id;
            const timeAgo = formatDistanceToNow(new Date(record.resolved_at || record.created_at), {
              addSuffix: true,
              locale,
            });

            return (
              <div key={record.id} className="p-4 transition-colors hover:bg-muted/30">
                <div className="flex items-start justify-between gap-4">
                  <div
                    className="flex-1 min-w-0 cursor-pointer group"
                    onClick={() => setExpandedId(isExpanded ? null : record.id)}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      {getStatusIcon(record.status)}
                      <h4 className="font-medium text-sm group-hover:text-primary transition-colors truncate">
                        {record.skill_name}
                      </h4>
                      <Badge variant="outline" className="text-[10px] py-0 h-4 px-1.5 font-mono">
                        {record.evolution_type}
                      </Badge>
                      <Badge
                        variant="secondary"
                        className={cn(
                          'text-[10px] py-0 h-4 px-1.5 font-mono',
                          record.status === 'approved' && 'bg-green-500/10 text-green-600 dark:text-green-400',
                          record.status === 'rolled_back' && 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400',
                          record.status === 'rejected' && 'bg-red-500/10 text-red-600 dark:text-red-400',
                        )}
                      >
                        {t(`status.${record.status}`)}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground line-clamp-1 mb-1">{record.reason}</p>
                    <div className="flex items-center gap-3 text-[10px] text-muted-foreground/70">
                      <span>{timeAgo}</span>
                      <span>ID: {record.skill_id.split('::').pop()}</span>
                    </div>
                  </div>

                  {record.status === 'approved' && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleRollback(record.id, record.skill_name)}
                      disabled={isRollingBack === record.id}
                      className="h-8 shrink-0 text-xs gap-1.5 border-dashed"
                    >
                      <Undo2 className="h-3.5 w-3.5" />
                      {t('rollback')}
                    </Button>
                  )}
                </div>

                {isExpanded && (
                  <div className="mt-4 pt-4 border-t border-border/40 animate-in fade-in slide-in-from-top-2 duration-200">
                    <div className="mb-2 text-xs font-medium text-muted-foreground">{t('codeChanges')}</div>
                    <div className="rounded-full border overflow-hidden bg-background h-[300px]">
                      <DiffEditor
                        height="300px"
                        original={record.original_content}
                        modified={record.evolved_content}
                        language="python"
                        theme={theme === 'dark' ? 'vs-dark' : 'light'}
                        options={{
                          readOnly: true,
                          renderSideBySide: false,
                          minimap: { enabled: false },
                          scrollBeyondLastLine: false,
                          wordWrap: 'on',
                          lineNumbersMinChars: 3,
                          padding: { top: 12, bottom: 12 },
                        }}
                      />
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default SkillHistoryPanel;
