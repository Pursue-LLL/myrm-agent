'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  AlertCircle,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  GitCommit,
  Loader2,
  MessageSquare,
  RefreshCw,
  ShieldCheck,
  Timer,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils/classnameUtils';
import { getDailyJournal, type DailyJournalData, type DailyJournalTimelineItem } from '@/services/statistics';
import { showApiError } from '@/lib/api';

function formatDateISO(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function formatTime(iso: string | null): string {
  if (!iso) return '--:--';
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

interface TypeStyle {
  icon: LucideIcon;
  text: string;
  bg: string;
  label: string;
}

const TYPE_CONFIG: Record<string, TypeStyle> = {
  session: { icon: MessageSquare, text: 'text-blue-500', bg: 'bg-blue-500/10', label: 'Session' },
  approval: { icon: ShieldCheck, text: 'text-amber-500', bg: 'bg-amber-500/10', label: 'Approval' },
  cron_run: { icon: Timer, text: 'text-green-500', bg: 'bg-green-500/10', label: 'Cron' },
  kanban: { icon: Workflow, text: 'text-purple-500', bg: 'bg-purple-500/10', label: 'Kanban' },
};

export default function DailyJournal() {
  const t = useTranslations('growthDashboard.dailyJournal');
  const [date, setDate] = useState(() => formatDateISO(new Date()));
  const [data, setData] = useState<DailyJournalData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(false);
      const result = await getDailyJournal(date);
      setData(result);
    } catch (e) {
      showApiError(e);
      setData(null);
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const shiftDay = (delta: number) => {
    const d = new Date(date + 'T00:00:00');
    d.setDate(d.getDate() + delta);
    if (d <= new Date()) setDate(formatDateISO(d));
  };

  const isToday = date === formatDateISO(new Date());

  return (
    <div className="space-y-4">
      {/* Date selector */}
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" onClick={() => shiftDay(-1)}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-muted text-sm font-medium">
          <CalendarDays className="h-4 w-4 text-muted-foreground" />
          <input
            type="date"
            value={date}
            max={formatDateISO(new Date())}
            onChange={(e) => setDate(e.target.value)}
            className="bg-transparent border-none outline-none text-foreground dark:[color-scheme:dark]"
          />
        </div>
        <Button variant="ghost" size="icon" onClick={() => shiftDay(1)} disabled={isToday}>
          <ChevronRight className="h-4 w-4" />
        </Button>
        {!isToday && (
          <Button variant="ghost" size="sm" onClick={() => setDate(formatDateISO(new Date()))}>
            {t('today')}
          </Button>
        )}
        <Button variant="ghost" size="icon" onClick={fetchData} className="ml-auto">
          <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
        </Button>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {!loading && error && (
        <div className="flex flex-col items-center justify-center py-16 gap-3 text-muted-foreground">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm">{t('error')}</p>
          <Button variant="outline" size="sm" onClick={fetchData}>
            {t('retry')}
          </Button>
        </div>
      )}

      {!loading && !error && data && (
        <>
          {/* Overview KPI cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <KpiMini label={t('sessions')} value={data.overview.total_sessions} />
            <KpiMini label={t('tokens')} value={data.overview.total_tokens.toLocaleString()} />
            <KpiMini label={t('cost')} value={`$${data.overview.total_cost_usd.toFixed(2)}`} />
            <KpiMini label={t('toolCalls')} value={data.overview.total_tool_calls} />
          </div>

          {/* Source breakdown badges */}
          {Object.keys(data.overview.sessions_by_source).length > 1 && (
            <div className="flex gap-2 flex-wrap">
              {Object.entries(data.overview.sessions_by_source).map(([src, count]) => (
                <Badge key={src} variant="secondary" className="text-xs">
                  {src}: {count}
                </Badge>
              ))}
            </div>
          )}

          {/* Timeline */}
          {data.timeline.length > 0 ? (
            <Card>
              <CardHeader className="pb-2 px-4 pt-4">
                <CardTitle className="text-base font-semibold">{t('timeline')}</CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4">
                <div className="space-y-1">
                  {data.timeline.map((item, i) => (
                    <TimelineRow key={i} item={item} />
                  ))}
                </div>
              </CardContent>
            </Card>
          ) : (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <GitCommit className="h-10 w-10 mb-3 opacity-30" />
              <p className="text-sm">{t('empty')}</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function KpiMini({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold text-foreground">{value}</p>
    </div>
  );
}

function TimelineRow({ item }: { item: DailyJournalTimelineItem }) {
  const cfg = TYPE_CONFIG[item.type] || TYPE_CONFIG.session;
  const Icon = cfg.icon;

  return (
    <div className="flex items-start gap-3 py-2 px-1 rounded-md hover:bg-muted/50 transition-colors">
      <span className="text-xs text-muted-foreground w-12 pt-0.5 shrink-0 text-right tabular-nums">
        {formatTime(item.time)}
      </span>
      <div className={cn('p-1.5 rounded-md shrink-0', cfg.bg)}>
        <Icon className={cn('h-3.5 w-3.5', cfg.text)} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-foreground truncate">{item.title}</p>
        {item.type === 'session' && item.detail?.tokens != null && (
          <p className="text-xs text-muted-foreground">
            {Number(item.detail.tokens).toLocaleString()} tokens · {String(item.detail.action_mode || '')}
          </p>
        )}
      </div>
      <Badge variant="outline" className="text-[10px] shrink-0">
        {cfg.label}
      </Badge>
    </div>
  );
}
