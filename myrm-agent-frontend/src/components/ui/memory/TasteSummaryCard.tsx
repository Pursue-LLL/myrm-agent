'use client';

import { memo, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Heart, Ban, Sparkles, Target, MessageSquare, Brain, Zap } from 'lucide-react';
import { IconGlow } from '@/components/ui/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { getTasteSummary, type TasteSummaryResponse } from '@/services/memory';

const TasteSummaryCard = memo<{ className?: string }>(({ className }) => {
  const t = useTranslations('memory.tasteSummary');
  const [data, setData] = useState<TasteSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getTasteSummary()
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading || !data) return null;

  const hasContent =
    data.style_keywords.length > 0 ||
    data.preference_keywords.length > 0 ||
    data.avoid_keywords.length > 0 ||
    (data.current_goals && data.current_goals.length > 0) ||
    !!data.reply_style ||
    !!data.technical_depth ||
    !!data.proactivity;

  if (!hasContent) return null;

  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-2xl border border-border/40 bg-gradient-to-br from-background/80 to-accent/20 p-5 shadow-sm backdrop-blur-xl',
        className,
      )}
    >
      {/* Decorative background glow */}
      <div className="absolute -right-20 -top-20 h-40 w-40 rounded-full bg-primary/5 blur-3xl" />
      <div className="absolute -bottom-20 -left-20 h-40 w-40 rounded-full bg-blue-500/5 blur-3xl" />

      <div className="relative z-10">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground">
          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10">
            <Sparkles className="h-3.5 w-3.5 text-primary" />
          </div>
          {t('title')}
        </h3>

        {data.summary && (
          <div className="mb-5 rounded-xl border border-primary/10 bg-primary/5 p-3.5">
            <p className="text-sm leading-relaxed text-foreground/90">{data.summary}</p>
          </div>
        )}

        <div className="space-y-3">
          {data.reply_style && (
            <KeywordRow
              icon={<MessageSquare className="h-3.5 w-3.5 text-blue-500" />}
              label={t('replyStyle') || '回复风格'}
              keywords={[data.reply_style]}
              color="blue"
            />
          )}
          {data.technical_depth && (
            <KeywordRow
              icon={<Brain className="h-3.5 w-3.5 text-indigo-500" />}
              label={t('technicalDepth') || '技术深度'}
              keywords={[data.technical_depth]}
              color="indigo"
            />
          )}
          {data.proactivity && (
            <KeywordRow
              icon={<Zap className="h-3.5 w-3.5 text-amber-500" />}
              label={t('proactivity') || '主动性'}
              keywords={[data.proactivity]}
              color="amber"
            />
          )}
          {data.current_goals && data.current_goals.length > 0 && (
            <KeywordRow
              icon={<Target className="h-3.5 w-3.5 text-purple-500" />}
              label={t('goals') || '当前目标'}
              keywords={data.current_goals}
              color="purple"
            />
          )}
          {data.style_keywords.length > 0 && (
            <KeywordRow
              icon={<IconGlow className="h-3.5 w-3.5 text-blue-500" />}
              label={t('style')}
              keywords={data.style_keywords}
              color="blue"
            />
          )}
          {data.preference_keywords.length > 0 && (
            <KeywordRow
              icon={<Heart className="h-3.5 w-3.5 text-emerald-500" />}
              label={t('preferences')}
              keywords={data.preference_keywords}
              color="green"
            />
          )}
          {data.avoid_keywords.length > 0 && (
            <KeywordRow
              icon={<Ban className="h-3.5 w-3.5 text-rose-500" />}
              label={t('avoid')}
              keywords={data.avoid_keywords}
              color="red"
            />
          )}
        </div>
      </div>
    </div>
  );
});

TasteSummaryCard.displayName = 'TasteSummaryCard';

const KeywordRow = memo<{
  icon: React.ReactNode;
  label: string;
  keywords: string[];
  color: 'blue' | 'green' | 'red' | 'purple' | 'indigo' | 'amber';
}>(({ icon, label, keywords, color }) => {
  const colorMap = {
    blue: 'border-blue-500/20 bg-blue-500/10 text-blue-600 dark:text-blue-400',
    green: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
    red: 'border-rose-500/20 bg-rose-500/10 text-rose-600 dark:text-rose-400',
    purple: 'border-purple-500/20 bg-purple-500/10 text-purple-600 dark:text-purple-400',
    indigo: 'border-indigo-500/20 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400',
    amber: 'border-amber-500/20 bg-amber-500/10 text-amber-600 dark:text-amber-400',
  };

  return (
    <div className="flex items-start gap-3">
      <div className="flex min-w-[70px] items-center gap-1.5 pt-1">
        {icon}
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {keywords.slice(0, 8).map((kw) => (
          <span
            key={kw}
            className={cn(
              'rounded-full border px-2.5 py-0.5 text-xs font-medium shadow-sm transition-colors hover:bg-background/80',
              colorMap[color],
            )}
          >
            {kw}
          </span>
        ))}
      </div>
    </div>
  );
});

KeywordRow.displayName = 'KeywordRow';

export default TasteSummaryCard;
